from decimal import Decimal
from typing import Optional, Dict, Any, List
import pyupbit
import pandas as pd
import numpy as np
import logging
import time

from strategy.base import StrategyBase
from strategy.models import StrategyContext, StrategyConfig, Signal, SignalType, StrategyType

logger = logging.getLogger(__name__)

# Optional Imports for Deep Learning
try:
    import torch
    import torch.nn as nn
    from sklearn.preprocessing import StandardScaler
    import joblib
    HAS_DL_LIBS = True
except ImportError:
    HAS_DL_LIBS = False
    logger.warning("Deep Learning libraries (torch, sklearn) not found. DeepAnomalyStrategy will not function.")

class DeepAnomalyStrategyConfig(StrategyConfig):
    name: str = "deep_anomaly_strategy"
    type: StrategyType = StrategyType.BUY
    
    execution_interval: int = 60  # Check every minute
    
    # Data Para
    train_lookback: int = 1000    # Number of candles to train on (e.g., 1000 mins)
    window_size: int = 30         # Sequence length for LSTM (30 mins)
    
    # Model Params
    hidden_size: int = 16
    num_layers: int = 1
    dropout: float = 0.1
    epochs: int = 20
    learning_rate: float = 0.005
    
    # Thresholding
    threshold_sigma: float = 3.0  # Anomaly if Loss > Mean + 3*Std
    
    buy_amount: Decimal
    
    class Config:
        arbitrary_types_allowed = True

if HAS_DL_LIBS:
    class LSTMAutoencoder(nn.Module):
        def __init__(self, input_size, hidden_size, num_layers=1, dropout=0.0):
            super(LSTMAutoencoder, self).__init__()
            self.input_size = input_size
            self.hidden_size = hidden_size
            
            # Encoder
            self.encoder = nn.LSTM(
                input_size=input_size, 
                hidden_size=hidden_size, 
                num_layers=num_layers, 
                batch_first=True,
                dropout=dropout
            )
            
            # Decoder
            self.decoder = nn.LSTM(
                input_size=hidden_size, # Input to decoder is the context vector (repeated? or seq?) 
                # Simplification: Standard AE often mirrors.
                # Here we use a simpler reconstruction: Encoder Last Hidden -> Decoder -> Output
                # To reconstruct sequence, we usually repeat the vector or use Seq2Seq.
                # Let's use a simple reconstruction LSTM that takes (Batch, Seq, Hidden).
                # Wait, Encoder outputs (Batch, Seq, Hidden).
                
                # Symmetrical Autoencoder:
                hidden_size=hidden_size,
                num_layers=num_layers, 
                batch_first=True,
                dropout=dropout
            )
            
            self.output_layer = nn.Linear(hidden_size, input_size)

        def forward(self, x):
            # x: (Batch, Seq, Feature)
            
            # Encoder
            enc_out, (h_n, c_n) = self.encoder(x)
            # enc_out: (Batch, Seq, Hidden)
            # h_n: (Layers, Batch, Hidden)
            
            # Decoder
            # We treat 'enc_out' as the latent representation for each step (preserving temporal info)
            # Or we can use h_n only. 
            # To detect point anomalies in sequence, mapping Sequence -> Sequence is good.
            
            dec_out, _ = self.decoder(enc_out)
            # dec_out: (Batch, Seq, Hidden)
            
            # Reconstruction
            recon = self.output_layer(dec_out)
            # recon: (Batch, Seq, Feature)
            
            return recon

class DeepAnomalyStrategy(StrategyBase):
    """
    Anomaly Detection using LSTM Autoencoder.
    Trains online on recent history.
    """
    ConfigModel = DeepAnomalyStrategyConfig

    def __init__(self, context: StrategyContext, config: DeepAnomalyStrategyConfig):
        super().__init__(context, config)
        self.config: DeepAnomalyStrategyConfig = config
        self.logger = logger
        self.model = None
        self.scaler = StandardScaler()
        self.last_train_time = 0
        self.train_interval = 3600 * 6 # Retrain every 6 hours? Or pure online?
        # For simplicity: Retrain if model is None or forced.
        # Actually retraining every call is too slow.
        # We'll train once on startup (first schedule) then update?
        
    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        return None

    def on_schedule(self) -> Optional[Signal]:
        if not HAS_DL_LIBS:
            return None
            
        try:
            # 1. Fetch Data
            # We need enough data for Training (lookback) + Window
            count = self.config.train_lookback + self.config.window_size + 10
            df = pyupbit.get_ohlcv(self.context.ticker, interval="minute1", count=count)
            
            if df is None or len(df) < count:
                self.logger.warning(f"Not enough data for Deep Learning: {len(df) if df is not None else 0}")
                return None
            
            # 2. Preprocessing
            # Use Log scale or Normalize?
            # Standardize 'close' price.
            # Using Returns is closer to stationary.
            # Let's use Log Returns.
            df['close'] = df['close'].astype(float)
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            df = df.dropna()
            
            if len(df) < self.config.train_lookback:
                return None

            data = df['log_return'].values.reshape(-1, 1) # (N, 1)

            # Split Train / Test (Current)
            # Train on history, Test on recent window
            # Actually for Anomaly Detection, we assume recent history is "normal" mostly.
            # We train on past N samples.
            
            train_data = data[-(self.config.train_lookback + self.config.window_size) : -1] # Exclude current?
            # Or train on all except very recent?
            
            # Normalize
            if self.last_train_time == 0 or (time.time() - self.last_train_time > self.train_interval):
                 needs_training = True
                 self.scaler.fit(train_data)
            else:
                 needs_training = False
            
            train_scaled = self.scaler.transform(train_data)
            
            # Prepare Sequences
            def create_sequences(d, window):
                xs = []
                for i in range(len(d) - window):
                    x = d[i : i+window]
                    xs.append(x)
                return np.array(xs)

            X_train = create_sequences(train_scaled, self.config.window_size)
            
            # Convert to Tensor
            X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
            
            # 3. Model Training (If needed)
            if self.model is None or needs_training:
                self.logger.info(f"Training LSTM Autoencoder for {self.context.ticker}...")
                self._train_model(X_train_tensor)
                self.last_train_time = time.time()
                
            # 4. Inference (Current Window)
            # Get latest window
            current_window = data[-self.config.window_size:] 
            if len(current_window) != self.config.window_size:
                return None
                
            current_scaled = self.scaler.transform(current_window) 
            X_curr_tensor = torch.tensor(current_scaled.reshape(1, self.config.window_size, 1), dtype=torch.float32)
            
            self.model.eval()
            with torch.no_grad():
                reconstruction = self.model(X_curr_tensor)
                loss = nn.MSELoss()(reconstruction, X_curr_tensor).item()
                
            # 5. Threshold Calculation (Dynamic)
            # Calculate MSE on Training Set to find "Normal" error distribution
            # Optimization: Do this only after training and cache it?
            if not hasattr(self, 'train_loss_mean'):
                self.model.eval()
                with torch.no_grad():
                    train_recon = self.model(X_train_tensor)
                    # MSE per sample
                    losses = torch.mean((train_recon - X_train_tensor)**2, dim=[1, 2])
                    self.train_loss_mean = losses.mean().item()
                    self.train_loss_std = losses.std().item()

            threshold = self.train_loss_mean + (self.config.threshold_sigma * self.train_loss_std)
            
            # 6. Signal Generation
            current_return = df.iloc[-1]['log_return']
            
            self.logger.debug(f"DL Loss: {loss:.6f}, Thr: {threshold:.6f} (Mean:{self.train_loss_mean:.6f}, Std:{self.train_loss_std:.6f})")
            
            if loss > threshold:
                # Anomaly Detected
                # Filter: Only Buy if Price is Dropping (Dip)
                # i.e., current_return should be negative (or sum of returns in window negative)
                
                is_dip = current_return < 0
                
                if is_dip:
                    reason = f"Deep Anomaly (Dip) Detected. Loss: {loss:.5f} > {threshold:.5f}"
                    self.logger.info(f"{reason} for {self.context.ticker}")
                    
                    return self.emit_signal(Signal(
                        type=SignalType.BUY,
                        strategy_id=self.context.strategy_id,
                        ticker=self.context.ticker,
                        amount=self.config.buy_amount,
                        reason=reason,
                        data={
                            "loss": loss,
                            "threshold": threshold,
                            "train_loss_mean": self.train_loss_mean
                        }
                    ))

        except Exception as e:
            self.logger.error(f"DL Strategy Error: {e}")
            # import traceback
            # self.logger.error(traceback.format_exc())
            
        return None

    def _train_model(self, X_train):
        input_dim = 1
        self.model = LSTMAutoencoder(input_dim, self.config.hidden_size, self.config.num_layers, self.config.dropout)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.config.learning_rate)
        criterion = nn.MSELoss()
        
        self.model.train()
        for epoch in range(self.config.epochs):
            optimizer.zero_grad()
            output = self.model(X_train)
            loss = criterion(output, X_train)
            loss.backward()
            optimizer.step()
            
        # Reset cached threshold stats
        if hasattr(self, 'train_loss_mean'):
            del self.train_loss_mean

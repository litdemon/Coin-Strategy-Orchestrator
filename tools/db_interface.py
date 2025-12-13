import sqlite3
import logging
from pydantic import BaseModel
from typing import Any, get_type_hints, TypeVar, Type, List, Dict
from decimal import Decimal
import json

# Decimal을 string으로 저장하도록 어댑터 등록
sqlite3.register_adapter(Decimal, str)
sqlite3.register_converter("DECIMAL", lambda v: Decimal(v.decode('utf-8')))

# List/Dict를 JSON string으로 저장하도록 어댑터 등록
sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)
sqlite3.register_converter("LIST", lambda v: json.loads(v.decode('utf-8')))
sqlite3.register_converter("DICT", lambda v: json.loads(v.decode('utf-8')))

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

DB_PATH = "database.db"
class DBInterface:
    """
    Pydantic 모델에 SQLite 저장 기능을 추가하는 Mixin 클래스
    """

    @classmethod
    def _get_table_name(cls) -> str:
        """클래스 이름을 소문자 + s 형태로 변환 (예: User -> users)"""
        return cls.__name__.lower() + "s"

    @classmethod
    def _map_type_to_sql(cls, py_type: Any) -> str:
        """파이썬 타입을 SQLite 타입으로 매핑"""
        if py_type == int:
            return "INTEGER"
        elif py_type == float:
            return "REAL"
        elif py_type == list or py_type == List or getattr(py_type, '__origin__', None) == list:
            return "LIST"
        elif py_type == dict or py_type == Dict or getattr(py_type, '__origin__', None) == dict:
            return "DICT"
        else:
            return "TEXT"  # str, bool 및 기타 타입은 TEXT로 저장

    @classmethod
    def init_db(cls, db_path: str = DB_PATH):
        """
        [Class Method]
        Pydantic 필드 정보를 읽어 테이블이 없으면 생성합니다.
        사용법: User.init_db('my.db')
        """
        table_name = cls._get_table_name()
        
        # Pydantic 모델의 필드 정의 가져오기 (v2 기준)
        fields = cls.model_fields  
        
        # 컬럼 정의 생성 (예: name TEXT, age INTEGER)
        columns_def = []
        
        # Pydantic v2에서는 annotation으로 타입을 확인합니다.
        for field_name, field_info in fields.items():
            if field_name == 'id':
                continue
            # 필드 타입 확인 (Optional 등 복잡한 타입은 간소화 처리)
            field_type = field_info.annotation
            sql_type = cls._map_type_to_sql(field_type)
            columns_def.append(f"{field_name} {sql_type}")
        
        query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {', '.join(columns_def)}
            )
        """
        
        archive_table_name = f"{table_name}_archive"
        archive_query = f"""
            CREATE TABLE IF NOT EXISTS {archive_table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {', '.join(columns_def)}
            )
        """
        
        # timeout 10초 설정
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            cursor.execute(archive_query)
            conn.commit()
            logger.info(f"[{table_name}, {archive_table_name}] 테이블 초기화 완료 (경로: {db_path})")

    def save(self, db_path: str = "database.db"):

        """
        [Instance Method]
        현재 인스턴스의 데이터를 DB에 저장합니다.
        사용법: user_instance.save('my.db')
        """
        # self는 Pydantic 모델이자 DBInterface의 인스턴스임
        table_name = self.__class__._get_table_name()
        
        # Pydantic v2: model_dump() 사용
        data = self.model_dump()
        
        keys = ", ".join(data.keys())
        placeholders = ", ".join([f":{k}" for k in data.keys()])
        
        query = f"INSERT INTO {table_name} ({keys}) VALUES ({placeholders})"
        
        
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(query, data)
            conn.commit()
            # 보안상 전체 데이터 로깅 제거
            logger.debug(f"데이터 저장 완료: {table_name}")
    
    @classmethod
    def save_all(cls, objects: List['DBInterface'], db_path: str = "database.db"):
        """
        리스트에 있는 모든 객체를 한 번의 DB 연결로 저장합니다.
        속도가 훨씬 빠릅니다.
        """
        if not objects:
            return

        table_name = cls._get_table_name()
        
        # 1. 첫 번째 객체를 기준으로 컬럼명과 쿼리 템플릿 생성
        # (모든 객체는 같은 클래스이므로 구조가 같다고 가정)
        first_obj = objects[0]
        sample_data = first_obj.model_dump(exclude={'id'})
        
        keys = ", ".join(sample_data.keys())
        placeholders = ", ".join([f":{k}" for k in sample_data.keys()])
        
        query = f"INSERT INTO {table_name} ({keys}) VALUES ({placeholders})"
        
        # 2. 저장할 데이터를 리스트 딕셔너리(List[Dict]) 형태로 변환
        data_list = [obj.model_dump(exclude={'id'}) for obj in objects]
        
        # 3. 한 번의 트랜잭션으로 모두 실행
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            # executemany는 내부적으로 최적화된 루프를 돕니다.
            conn.executemany(query, data_list)
            conn.commit()
            logger.info(f"[{len(objects)}]건 대량 저장 완료.")

    @classmethod
    def load_all(cls: Type[T], db_path: str = DB_PATH) -> List[T]:
        """
        DB의 모든 데이터를 읽어와서 Pydantic 객체의 리스트로 반환
        """
        table_name = cls._get_table_name()
        query = f"SELECT * FROM {table_name}"
        
        results = []
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            # Row Factory 설정: DB 결과를 딕셔너리처럼 컬럼명으로 접근 가능하게 함
            conn.row_factory = sqlite3.Row 
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            
            for row in rows:
                # 1. Row 객체를 딕셔너리로 변환
                row_dict = dict(row)
                
                # 2. 딕셔너리를 사용하여 Pydantic 객체 생성 (**Unpacking)
                # DB의 'id' 컬럼도 row_dict에 포함되어 있으므로 모델에 id 필드가 있으면 자동 매핑됨
                instance = cls(**row_dict)
                results.append(instance)
                
        return results

    def archive(self, db_path: str = DB_PATH):
        """
        [Instance Method]
        현재 인스턴스의 데이터를 아카이브 테이블로 이동하고 메인 테이블에서 삭제합니다.
        사용법: user_instance.archive()
        """
        table_name = self.__class__._get_table_name()
        archive_table_name = f"{table_name}_archive"
        
        # Pydantic v2: model_dump() 사용
        data = self.model_dump()
        
        # id가 있어야 삭제 및 이동이 가능함
        if 'id' not in data:
            logger.error(f"Archive 실패: id가 없습니다. {data}")
            return

        keys = ", ".join(data.keys())
        placeholders = ", ".join([f":{k}" for k in data.keys()])
        
        insert_query = f"INSERT INTO {archive_table_name} ({keys}) VALUES ({placeholders})"
        delete_query = f"DELETE FROM {table_name} WHERE id = :id"
        
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            cursor = conn.cursor()
            try:
                # 1. 아카이브 테이블에 복사
                cursor.execute(insert_query, data)
                # 2. 메인 테이블에서 삭제
                cursor.execute(delete_query, {'id': data['id']})
                conn.commit()
                logger.info(f"데이터 아카이브 완료: ID {data.get('id')}")
            except Exception as e:
                conn.rollback()
                logger.error(f"데이터 아카이브 실패: {e}")
                raise e

import unittest
import os
import sqlite3
from typing import Optional
from pydantic import Field
from tools.db_interface import DBInterface
from pydantic import BaseModel

TEST_DB_PATH = "test_archive.db"

class TestModel(BaseModel, DBInterface):
    id: Optional[int] = None
    name: str
    value: int

class TestDBArchive(unittest.TestCase):
    def setUp(self):
        # 테스트 전 DB 초기화
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        TestModel.init_db(TEST_DB_PATH)

    def tearDown(self):
        # 테스트 후 DB 정리
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_archive(self):
        # 1. 데이터 생성 및 저장
        item = TestModel(name="test_item", value=100)
        item.save(TEST_DB_PATH)
        
        # ID가 자동 생성되었는지 확인 (DB에서 다시 로드하거나 save 로직에 따라 다를 수 있음)
        # 현재 save 구현은 id 반환을 안하므로, load_all로 가져와서 확인
        items = TestModel.load_all(TEST_DB_PATH)
        self.assertEqual(len(items), 1)
        loaded_item = items[0]
        self.assertEqual(loaded_item.name, "test_item")
        
        # 2. 아카이브 실행
        loaded_item.archive(TEST_DB_PATH)
        
        # 3. 메인 테이블에서 삭제되었는지 확인
        items_after_archive = TestModel.load_all(TEST_DB_PATH)
        self.assertEqual(len(items_after_archive), 0)
        
        # 4. 아카이브 테이블에 존재하는지 확인
        with sqlite3.connect(TEST_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM testmodels_archive")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1], "test_item") # 0 is id, 1 is name
            self.assertEqual(rows[0][2], 100) # 2 is value

if __name__ == '__main__':
    unittest.main()

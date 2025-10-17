from app.db_repo import DbRepo
from app.db_service import DbService

db_repo = DbRepo()
db_service = DbService(db_repo)

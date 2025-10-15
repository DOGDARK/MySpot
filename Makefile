lint:
	ruff format .
	ruff check --fix .

up_db:
	docker compose up -d

down_db:
	docker compose down
	


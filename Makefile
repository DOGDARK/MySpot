lint:
	ruff format .
	ruff check --fix .

up:
	docker compose -f docker-compose.prod.yml up -d

up_db:
	docker compose -f docker-compose.prod.yml up db -d	

up_loader:
	docker compose -f docker-compose.loader.prod.yml up -d

down:
	docker compose -f docker-compose.prod.yml down

build:
	docker build -t my_spot:latest .

up_local:
	docker compose up -db

down_local:
	docker compose down
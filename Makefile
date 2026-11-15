SHELL := /bin/bash
VENV := ./.venv/bin

.PHONY: dev api front install build test

## dev : lance le back (FastAPI :8000) et le front (Vite :5173) ensemble
dev:
	@echo "Back → http://localhost:8000/docs   |   Front → http://localhost:5173"
	@trap 'kill 0' EXIT; \
	$(VENV)/uvicorn api.main:app --port 8000 & \
	( cd frontend && npm run dev ) & \
	wait

## api : back seul (avec reload)
api:
	$(VENV)/uvicorn api.main:app --reload --port 8000

## front : front seul
front:
	cd frontend && npm run dev

## install : dépendances back + front
install:
	$(VENV)/pip install -r requirements.txt
	cd frontend && npm install --no-fund --no-audit

## test : tests du back (base jetable, sans réseau)
test:
	$(VENV)/python -m pytest -q

## build : build de production du front
build:
	cd frontend && npm run build

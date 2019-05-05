.PHONY: fmt run

all: fmt run

fmt:
	isort src/*.py
	black -S src/*.py

run:
	python src/main.py

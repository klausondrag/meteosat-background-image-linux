.PHONY: fmt help run

all: fmt help run

fmt:
	isort src/*.py
	black -S src/*.py

help:
	python src/main.py --help

run:
	python src/main.py

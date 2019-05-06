.PHONY: fmt help build run

all: fmt help run build

build:
	pyinstaller --onefile src/main.py

fmt:
	isort src/*.py
	black -S src/*.py

help:
	python src/main.py --help

run:
	python src/main.py

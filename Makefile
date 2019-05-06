.PHONY: build copy fmt help run

all: fmt help run

build:
	pyinstaller --onefile src/main.py

copy:
	cp dist/main ~/.local/bin/meteosat-background-image

fmt:
	isort src/*.py
	black -S src/*.py

help:
	python src/main.py --help

run:
	python src/main.py

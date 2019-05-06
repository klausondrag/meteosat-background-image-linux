.PHONY: build copy fmt help run
all: fmt help run

file = src/main.py

build:
	pyinstaller --onefile $(file)

copy:
	cp dist/main ~/.local/bin/meteosat-background-image

fmt:
	isort src/*.py
	black -S src/*.py

help:
	python $(file) --help

run:
	python $(file)

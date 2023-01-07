
.PHONY:: dist up

dist:
	# If bdist_wheel does not work:
	# pip install wheel twine
	python setup.py sdist bdist_wheel

testup:
	twine upload -r testpypi dist/*

up:
	twine upload dist/*

init:
	python3 -m venv ./venv
	./venv/bin/pip install -U pip wheel twine
	./venv/bin/pip install -U -r requirements.txt

.PHONY: build package publish clean test docs docs-zip

PACKAGE_NAME := riscos-artworks
VERSION ?= $(shell ./ci-vars --json | python3 -c 'import json, sys; print(json.load(sys.stdin)["CI_PROJECT_VERSION"])')
WHEEL_VERSION ?= $(shell python3 -c 'import re, sys; parts = sys.argv[1].split("."); numbers = []; [numbers.append(parts.pop(0)) for _ in range(len(parts)) if parts and parts[0].isdigit()]; base = ".".join(numbers) or "0"; suffix = ".".join(parts); print(base + (("+" + re.sub(r"[^a-zA-Z0-9]+", ".", suffix).strip(".")) if suffix else ""))' '$(VERSION)')
# The ci-vars version may contain a branch name (eg 'ci/some-work'), but a
# Debian 'Version:' field, and the file names we build from it, only permit
# [A-Za-z0-9.+~]. Replace any run of other characters with '.'.
DEB_VERSION ?= $(shell printf '%s' '$(VERSION)' | sed -E 's/[^A-Za-z0-9.+~]+/./g')
BUILD_SOURCE := build/source
PACKAGE_DIR := build/$(PACKAGE_NAME)_$(DEB_VERSION)_all
PACKAGE_FILE := dist/$(PACKAGE_NAME)_$(DEB_VERSION)_all.deb
DOCS_SOURCES := docs/artworks-fileformat.xml
DOCS_DIR := output/docs
DOCS_FILE := $(PACKAGE_NAME)-$(DEB_VERSION)-docs.zip

build:
	rm -rf "$(BUILD_SOURCE)" dist
	mkdir -p "$(BUILD_SOURCE)/src"
	cp -a README.md LICENSE PLAN.md MANIFEST.in scripts tests "$(BUILD_SOURCE)/"
	cp -a src/riscos_artworks "$(BUILD_SOURCE)/src/riscos_artworks"
	find "$(BUILD_SOURCE)" -name __pycache__ -type d -prune -exec rm -rf {} +
	sed 's/^version = ".*"/version = "$(WHEEL_VERSION)"/' pyproject.toml > "$(BUILD_SOURCE)/pyproject.toml"
	# The in-tree __version__ is "dev"; the built copy carries the real one.
	sed -i 's/^__version__ = ".*"/__version__ = "$(WHEEL_VERSION)"/' "$(BUILD_SOURCE)/src/riscos_artworks/__init__.py"
	python3 -m build --outdir "$(CURDIR)/dist" "$(BUILD_SOURCE)"

package:
	$(MAKE) clean build
	mkdir -p "$(PACKAGE_DIR)/DEBIAN" \
		"$(PACKAGE_DIR)/usr/share/doc/$(PACKAGE_NAME)"
	python3 -m pip install --root "$(PACKAGE_DIR)" --prefix /usr \
		--no-deps --no-compile --ignore-installed dist/*.whl
	cp README.md LICENSE "$(PACKAGE_DIR)/usr/share/doc/$(PACKAGE_NAME)/"
	printf '%s\n' \
		'Package: $(PACKAGE_NAME)' \
		'Version: $(DEB_VERSION)' \
		'Section: utils' \
		'Priority: optional' \
		'Architecture: all' \
		'Maintainer: Charles Ferguson <gerph@gerph.org>' \
		'Depends: python3 (>= 3.11)' \
		'Description: Structural decoder for Computer Concepts ArtWorks files' \
		' Decode RISC OS ArtWorks documents into a structural record tree,' \
		' dump them as text or JSON, and audit collections of files, with' \
		' the riscos-artworks command.' \
		> "$(PACKAGE_DIR)/DEBIAN/control"
	mkdir -p dist
	dpkg-deb --build --root-owner-group "$(PACKAGE_DIR)" "$(PACKAGE_FILE)"

# Build the PRM-in-XML documentation with the local riscos-prminxml tool,
# then archive it. CI environments which generate the HTML another way
# (eg the GitHub action) can populate $(DOCS_DIR) themselves and call
# 'docs-zip' directly, so that the archive is named identically everywhere.
docs:
	rm -rf "$(DOCS_DIR)"
	mkdir -p "$(DOCS_DIR)"
	riscos-prminxml -f html5+xml -O "$(DOCS_DIR)" $(DOCS_SOURCES)
	$(MAKE) docs-zip

docs-zip:
	rm -f "$(DOCS_FILE)"
	cd "$(DOCS_DIR)" && zip -9r "$(CURDIR)/$(DOCS_FILE)" *

publish: build
	python3 -m twine upload dist/*

clean:
	rm -rf dist/ build/ output/ *.egg-info *-docs.zip

test:
	PYTHONPATH="src$${PYTHONPATH:+:$$PYTHONPATH}" python3 -m unittest discover -s tests

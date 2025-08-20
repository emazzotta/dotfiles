.DEFAULT_GOAL := build

.PHONY: build run shell stop clean fetch-dotfiles update-dotfiles

DOTFILES_REPO ?= https://github.com/emazzotta/dotfiles.git
DOTFILES_DIR  ?= dotfiles

fetch-dotfiles:
	@if [ -d "$(DOTFILES_DIR)/.git" ]; then \
		echo ">> Updating $(DOTFILES_DIR)"; \
		git -C "$(DOTFILES_DIR)" fetch --all --prune; \
		git -C "$(DOTFILES_DIR)" pull --rebase --autostash; \
		git -C "$(DOTFILES_DIR)" submodule update --init --recursive; \
	else \
		echo ">> Cloning $(DOTFILES_REPO) into $(DOTFILES_DIR)"; \
		git clone --recurse-submodules "$(DOTFILES_REPO)" "$(DOTFILES_DIR)"; \
	fi

update-dotfiles: fetch-dotfiles

build: fetch-dotfiles
	@docker-compose build

run:
	@docker-compose up -d --remove-orphans

shell: run
	@docker-compose exec dev /bin/bash

stop:
	@docker-compose down

clean:
	@docker-compose down -v
	@rm -rf workspace dotfiles

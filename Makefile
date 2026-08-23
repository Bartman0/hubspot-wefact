IMAGE_NAME := $(shell uv version | cut -d ' ' -f 1)
TAG        := latest
IMAGE      := creathlon/$(IMAGE_NAME):$(TAG)
STAMP      := .docker-build-stamp

.PHONY: all build run

DEPENDENCIES := Dockerfile $(shell find . -type f -name "*.py" 2>/dev/null)

all: run

build: $(STAMP)

$(STAMP): $(DEPENDENCIES)
	@echo "🛠️ Source or Dockerfile changed. Building image..."
	docker build . -t $(IMAGE) --platform linux/amd64
	@# Update the modified time of the stamp file (or create it)
	touch $(STAMP)

run: build
	@echo "🚀 Running Docker container..."
	docker run --rm -it \
	 -e HUBSPOT_ACCESS_TOKEN -e WEFACT_API_KEY \
	 -v ./data:/app/data \
	 $(IMAGE)

clean:
	@echo "🧹 Cleaning up..."
	rm -f $(STAMP)

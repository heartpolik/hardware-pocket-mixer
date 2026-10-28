# Desktop builds of the firmware core: simulator (SDL2) and tests. The Teensy build is PlatformIO
# (platformio.ini). Run from firmware/:  make sim && ./build/pocket-mixer-sim ;  make test
CXX ?= clang++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -g
CORE := $(wildcard src/core/*.cpp)
HDRS := $(wildcard src/core/*.h) $(wildcard sim/*.h)
SDL_CFLAGS := $(shell sdl2-config --cflags 2>/dev/null)
SDL_LIBS := $(shell sdl2-config --libs 2>/dev/null)

all: sim test

build:
	mkdir -p build

sim: build/pocket-mixer-sim
build/pocket-mixer-sim: $(CORE) sim/main.cpp $(HDRS) | build
	$(CXX) $(CXXFLAGS) $(SDL_CFLAGS) -o $@ $(CORE) sim/main.cpp $(SDL_LIBS) -lz

test: build/test-core
	./build/test-core
build/test-core: $(CORE) tests/test_core.cpp $(HDRS) | build
	$(CXX) $(CXXFLAGS) -o $@ $(CORE) tests/test_core.cpp

font:
	python3 tools/gen_font.py

clean:
	rm -rf build

.PHONY: all sim test font clean

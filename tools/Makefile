# ==============================================================================
# Makefile — tools/scrape_colorable
# ==============================================================================
# Targets:
#   make           Build optimised release binary  (default)
#   make debug     Build with debug symbols + ASan/UBSan
#   make clean     Remove compiled binaries
#   make help      Print this message
#
# Override compiler:  make CXX=clang++
# ==============================================================================

CXX      ?= g++
TARGET    = scrape_colorable
SRC       = scrape_colorable.cpp

# Release: full optimisation, auto-vectorise for the host CPU
CXXFLAGS_RELEASE = -std=c++17 -O3 -march=native -Wall -Wextra

# Debug: no optimisation, AddressSanitizer + UndefinedBehaviourSanitizer
CXXFLAGS_DEBUG   = -std=c++17 -O0 -g -Wall -Wextra \
                   -fsanitize=address,undefined -fno-omit-frame-pointer

.PHONY: all debug clean help

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS_RELEASE) -o $@ $<
	@echo "Built $@ (release)"

debug: $(SRC)
	$(CXX) $(CXXFLAGS_DEBUG) -o $(TARGET)_debug $<
	@echo "Built $(TARGET)_debug (debug + sanitisers)"

clean:
	rm -f $(TARGET) $(TARGET)_debug

help:
	@echo "Targets:"
	@echo "  make           Release build  → ./$(TARGET)"
	@echo "  make debug     Debug build    → ./$(TARGET)_debug"
	@echo "  make clean     Remove binaries"
	@echo ""
	@echo "Override compiler:  make CXX=clang++"

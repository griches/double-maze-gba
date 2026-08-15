#---------------------------------------------------------------------------------
.SUFFIXES:
#---------------------------------------------------------------------------------

ifeq ($(strip $(DEVKITARM)),)
$(error "Please set DEVKITARM in your environment. export DEVKITARM=<path to>devkitARM")
endif

include $(DEVKITARM)/gba_rules

#---------------------------------------------------------------------------------
# TARGET   is the name of the output, also the internal ROM title
# BUILD    is the directory where object files & intermediates are placed
# SOURCES  is a list of directories containing source code
# INCLUDES is a list of directories containing extra header files
# GRAPHICS is a list of directories containing .png files converted by grit
# MUSIC    is a directory of audio files built into a maxmod soundbank
#---------------------------------------------------------------------------------
TARGET   := double_maze
BUILD    := build
SOURCES  := source
DATA     :=
GRAPHICS := gfx
MUSIC    := audio
INCLUDES := source

#---------------------------------------------------------------------------------
# options for code generation
#---------------------------------------------------------------------------------
ARCH := -mthumb -mthumb-interwork

CFLAGS := -g -Wall -Wextra -O2 \
          -mcpu=arm7tdmi -mtune=arm7tdmi \
          -fomit-frame-pointer \
          -ffast-math \
          $(ARCH)

CFLAGS   += $(INCLUDE) $(DEFINES)
CXXFLAGS := $(CFLAGS) -fno-rtti -fno-exceptions

ASFLAGS  := -g $(ARCH)
LDFLAGS   = -g $(ARCH) -Wl,-Map,$(notdir $*.map)

#---------------------------------------------------------------------------------
# any extra libraries we wish to link with the project
#---------------------------------------------------------------------------------
# maxmod (-lmm) lives in libgba. We only ever include <maxmod.h> from there,
# so its headers don't collide with libtonc's.
LIBS := -ltonc -lmm

#---------------------------------------------------------------------------------
# list of directories containing libraries, this must be the top level
# containing include and lib.
# gba_rules defines LIBGBA for us but not LIBTONC, so do it here.
#---------------------------------------------------------------------------------
LIBTONC := $(DEVKITPRO)/libtonc
LIBDIRS := $(LIBTONC) $(LIBGBA)

#---------------------------------------------------------------------------------
# no real need to edit anything past this point unless you need to add
# additional rules for different file extensions
#---------------------------------------------------------------------------------
ifneq ($(BUILD),$(notdir $(CURDIR)))
#---------------------------------------------------------------------------------

export OUTPUT := $(CURDIR)/$(TARGET)

export VPATH := $(foreach dir,$(SOURCES),$(CURDIR)/$(dir)) \
                $(foreach dir,$(DATA),$(CURDIR)/$(dir)) \
                $(foreach dir,$(GRAPHICS),$(CURDIR)/$(dir))

export DEPSDIR := $(CURDIR)/$(BUILD)

CFILES   := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
CPPFILES := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
SFILES   := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))
BINFILES := $(foreach dir,$(DATA),$(notdir $(wildcard $(dir)/*.*)))
PNGFILES := $(foreach dir,$(GRAPHICS),$(notdir $(wildcard $(dir)/*.png)))

#---------------------------------------------------------------------------------
# mmutil packs every file in $(MUSIC) into one soundbank, which then goes
# through bin2o like any other binary blob.
#---------------------------------------------------------------------------------
ifneq ($(strip $(MUSIC)),)
    export AUDIOFILES := $(foreach file,$(notdir $(wildcard $(MUSIC)/*.*)),$(CURDIR)/$(MUSIC)/$(file))
    BINFILES += soundbank.bin
endif

#---------------------------------------------------------------------------------
# use CXX for linking C++ projects, CC for standard C
#---------------------------------------------------------------------------------
ifeq ($(strip $(CPPFILES)),)
    export LD := $(CC)
else
    export LD := $(CXX)
endif

export OFILES_BIN     := $(addsuffix .o,$(BINFILES))
export OFILES_GFX     := $(PNGFILES:.png=.o)
export OFILES_SOURCES := $(CPPFILES:.cpp=.o) $(CFILES:.c=.o) $(SFILES:.s=.o)
export OFILES         := $(OFILES_BIN) $(OFILES_GFX) $(OFILES_SOURCES)

export HFILES := $(PNGFILES:.png=.h) $(addsuffix .h,$(subst .,_,$(BINFILES)))
ifneq ($(strip $(MUSIC)),)
    # mmutil emits soundbank.h (the SFX_* ids) alongside soundbank_bin.h.
    export HFILES += soundbank.h
endif

export INCLUDE := $(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir)) \
                  $(foreach dir,$(LIBDIRS),-I$(dir)/include) \
                  -I$(CURDIR)/$(BUILD)

export LIBPATHS := $(foreach dir,$(LIBDIRS),-L$(dir)/lib)

MGBA := /Applications/mGBA.app/Contents/MacOS/mGBA

# $(BUILD) must be phony: it names a directory that always exists once we've
# built, and make would otherwise consider it up to date and skip the sub-make.
.PHONY: $(BUILD) all clean run assets levels audio shot

#---------------------------------------------------------------------------------
all: $(BUILD)

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

#---------------------------------------------------------------------------------
clean:
	@echo clean ...
	@rm -fr $(BUILD) $(TARGET).elf $(TARGET).gba $(TARGET).map

#---------------------------------------------------------------------------------
# Regenerate the tilesets from the original iOS artwork.
assets:
	@python3 tools/make_assets.py

#---------------------------------------------------------------------------------
# Regenerate the level tables from the original iOS level files.
levels:
	@python3 tools/extract_levels.py

#---------------------------------------------------------------------------------
# Re-encode the iOS audio into audio/*.wav for mmutil.
audio:
	@python3 tools/make_audio.py

#---------------------------------------------------------------------------------
# Screenshot the running ROM through mGBA's GDB stub. Override SHOT to name the
# output: make shot SHOT=title.png
SHOT ?= shot.png
shot: $(BUILD)
	@python3 tools/grab_screen.py $(SHOT) --rom $(CURDIR)/$(TARGET).gba --delay 3.0

#---------------------------------------------------------------------------------
# Build, then boot the ROM in mGBA.
run: $(BUILD)
	@echo running $(TARGET).gba ...
	@$(MGBA) $(CURDIR)/$(TARGET).gba

#---------------------------------------------------------------------------------
else

DEPENDS := $(OFILES:.o=.d)

#---------------------------------------------------------------------------------
# main targets
#---------------------------------------------------------------------------------
$(OUTPUT).gba : $(OUTPUT).elf

$(OUTPUT).elf : $(OFILES)

$(OFILES_SOURCES) : $(HFILES)

#---------------------------------------------------------------------------------
# Convert a .png (+ its .grit options file) into assembly and a header.
# devkitARM's rules don't supply this one -- it belongs to the project.
#---------------------------------------------------------------------------------
%.s %.h : %.png %.grit
	$(SILENTMSG) $(notdir $<)
	$(SILENTCMD)grit $< -fts -o$*

#---------------------------------------------------------------------------------
# Build the maxmod soundbank, then wrap any .bin as a linkable object.
#---------------------------------------------------------------------------------
soundbank.bin soundbank.h : $(AUDIOFILES)
	$(SILENTMSG) soundbank
	$(SILENTCMD)mmutil $^ -osoundbank.bin -hsoundbank.h

%.bin.o %_bin.h : %.bin
	$(SILENTMSG) $(notdir $<)
	$(bin2o)

-include $(DEPENDS)

#---------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------

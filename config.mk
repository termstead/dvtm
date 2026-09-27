# Customize below to fit your system

PREFIX ?= /usr/local
MANPREFIX = ${PREFIX}/share/man
# specify your systems terminfo directory
# leave empty to install into your home folder
TERMINFO := ${DESTDIR}${PREFIX}/share/terminfo

PKG_CONFIG ?= pkg-config
CURSES_INCS := $(shell ${PKG_CONFIG} --cflags-only-I ncursesw 2>/dev/null)
CURSES_LIBS := $(shell ${PKG_CONFIG} --libs ncursesw 2>/dev/null || echo -lncursesw)

INCS = -I. ${CURSES_INCS}
LIBS = -lc -lutil ${CURSES_LIBS}
CPPFLAGS = -D_POSIX_C_SOURCE=200809L -D_XOPEN_SOURCE=700 -D_XOPEN_SOURCE_EXTENDED
CFLAGS += -std=c99 ${INCS} -DNDEBUG ${CPPFLAGS}

CC ?= cc

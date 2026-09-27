/* Unit tests for the terminal emulator's color handling. */
#include <locale.h>
#include "../vt.c"

static int failures;

#define CHECK(cond) do { \
	if (!(cond)) { \
		fprintf(stderr, "%s:%d: %s: check failed: %s\n", __FILE__, __LINE__, term, #cond); \
		failures++; \
	} \
} while (0)

static const char *term;
static WINDOW *pad;

static void feed(Vt *t, const char *s)
{
	int fds[2];
	if (pipe(fds))
		abort();
	t->pty = fds[0];
	if (write(fds[1], s, strlen(s)) != (ssize_t)strlen(s))
		abort();
	close(fds[1]);
	vt_process(t);
	close(fds[0]);
	vt_draw(t, pad, 0, 0);
}

/* color pair content of the cell drawn at column x of the first row */
static void drawn(int x, int *fg, int *bg)
{
	cchar_t cc;
	attr_t attrs;
	int pair = 0;
	mvwin_wch(pad, 0, x, &cc);
	getcchar(&cc, (wchar_t[CCHARW_MAX + 1]){0}, &attrs, &(short){0}, &pair);
	extended_pair_content(pair, fg, bg);
}

static char *content(Vt *t)
{
	static char *buf;
	free(buf);
	size_t len = vt_content_get(t, &buf, true);
	buf = realloc(buf, len + 1);
	buf[len] = '\0';
	return buf;
}

static void test_term(const char *name, int red, int palette196, int rgb123, int rgb001)
{
	term = name;
	FILE *out = fopen("/dev/null", "w"), *in = fopen("/dev/null", "r");
	SCREEN *screen = newterm(name, out, in);
	if (!screen) {
		fprintf(stderr, "%s: terminal description missing, skipped\n", name);
		return;
	}
	set_term(screen);
	start_color();
	vt_init();
	pad = newpad(4, 80);
	int fg, bg;

	int reserved = vt_color_reserve(COLOR_BLUE, -1);
	CHECK(reserved > 0);

	Vt *t = vt_create(2, 80, 0);
	feed(t, "\033[31ma\033[38;5;196mb\033[38;2;255;0;0mc\033[48;2;1;2;3md");
	drawn(0, &fg, &bg);
	CHECK(fg == COLOR_RED);
	drawn(1, &fg, &bg);
	CHECK(fg == palette196);
	drawn(2, &fg, &bg);
	CHECK(fg == red);
	drawn(3, &fg, &bg);
	CHECK(fg == red && bg == rgb123);

	char *s = content(t);
	CHECK(strstr(s, "\033[38;5;1m\033[49ma"));
	CHECK(strstr(s, "\033[38;5;196mb"));
	CHECK(strstr(s, "\033[38;2;255;0;0mc"));
	CHECK(strstr(s, "\033[48;2;1;2;3md"));

	/* near black must not turn into one of the palette colors 0-7 */
	feed(t, "\033[H\033[38;2;0;0;1mx");
	drawn(0, &fg, &bg);
	CHECK(fg == rgb001);

	/* malformed sequences are ignored */
	feed(t, "\033[H\033[0;38;2;255;0mx\033[38;5;256my\033[38;2;1;2;300mz");
	s = content(t);
	CHECK(strstr(s, "\033[39m\033[49mxyz"));

	/* cycle through many pairs, the reserved one must survive */
	char seq[64];
	for (int i = 0; i < 70000; i += 7) {
		snprintf(seq, sizeof seq, "\033[H\033[38;2;%d;%d;0;48;5;%dmx", i & 0xff, (i >> 8) & 0xff, i % 256);
		feed(t, seq);
	}
	extended_pair_content(reserved, &fg, &bg);
	CHECK(fg == COLOR_BLUE && bg == -1);
	CHECK(vt_color_reserve(COLOR_BLUE, -1) == reserved);

	vt_destroy(t);
	delwin(pad);
	endwin();
	delscreen(screen);
	fclose(out);
	fclose(in);
}

int main(void)
{
	setlocale(LC_CTYPE, "C.UTF-8");

	/* a direct color terminal description, like xterm-direct */
	char dir[] = "/tmp/dvtm-test-XXXXXX", cmd[128];
	if (!mkdtemp(dir))
		return 1;
	snprintf(cmd, sizeof cmd, "tic -x -o %s - 2>/dev/null", dir);
	FILE *tic = popen(cmd, "w");
	if (!tic)
		return 1;
	fputs("dvtm-test-direct|direct color,\n"
	      "\tuse=xterm-256color, colors#0x1000000, pairs#0x10000, RGB,\n"
	      "\tsetaf=\\E[%?%p1%{8}%<%t3%p1%d%e38;2;%p1%{65536}%/%d;%p1%{256}%/%{255}%&%d;%p1%{255}%&%d%;m,\n"
	      "\tsetab=\\E[%?%p1%{8}%<%t4%p1%d%e48;2;%p1%{65536}%/%d;%p1%{256}%/%{255}%&%d;%p1%{255}%&%d%;m,\n", tic);
	bool direct = pclose(tic) == 0;
	setenv("TERMINFO", dir, 1);

	test_term("xterm", COLOR_RED, COLOR_RED, COLOR_BLACK, COLOR_BLACK);
	test_term("xterm-256color", 196, 196, 16, 16);
	if (direct)
		test_term("dvtm-test-direct", 0xff0000, 0xff0000, 0x010203, 8);
	else
		fprintf(stderr, "tic failed, direct color not tested\n");

	snprintf(cmd, sizeof cmd, "rm -rf %s", dir);
	if (system(cmd))
		failures++;
	if (failures)
		fprintf(stderr, "%d check(s) failed\n", failures);
	return failures != 0;
}

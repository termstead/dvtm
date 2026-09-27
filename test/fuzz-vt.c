/* libFuzzer harness: feed arbitrary bytes through the terminal emulator. */
#include <locale.h>
#include "../vt.c"

static WINDOW *pad;

int LLVMFuzzerInitialize(int *argc, char ***argv)
{
	setlocale(LC_CTYPE, "C.UTF-8");
	FILE *out = fopen("/dev/null", "w"), *in = fopen("/dev/null", "r");
	if (!out || !in || !newterm("xterm-256color", out, in))
		abort();
	start_color();
	vt_init();
	pad = newpad(256, 256);
	return 0;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
	int fds[2];
	if (size < 3 || pipe(fds))
		return 0;

	Vt *t = vt_create(1 + data[0] % 60, 1 + data[1] % 200, data[2] % 64);
	if (!t)
		abort();
	t->pty = fds[0];
	t->pid = getpid(); /* not a group leader: kill(-pid, SIGWINCH) is a no-op */
	fcntl(fds[0], F_SETFL, O_NONBLOCK);
	data += 3, size -= 3;

	while (size > 0) {
		size_t len = size < 4096 ? size : 4096;
		if (write(fds[1], data, len) != (ssize_t)len)
			abort();
		vt_process(t);
		vt_draw(t, pad, 0, 0);
		data += len, size -= len;
	}

	vt_scroll(t, -10);
	vt_draw(t, pad, 0, 0);
	char *buf = NULL;
	vt_content_get(t, &buf, true);
	free(buf);
	vt_resize(t, 5, 7);
	vt_draw(t, pad, 0, 0);

	close(fds[1]);
	vt_destroy(t);
	return 0;
}

/* theora_enc: a YUV4MPEG2 (4:2:0) stream on stdin -> an Ogg Theora file, video only, for Godot 4.7's
 * VideoStreamTheora. This Mac's ffmpeg has no libtheora encoder (its "x.ogv" is VP8), but Homebrew's libtheora and
 * libogg are installed, so ffmpeg decodes and this encodes:
 *
 *   python3.11 tools/video/to_ogv.py in.mp4 out.ogv          (builds this file on first use; see there)
 *   ffmpeg -i in.mp4 -an -pix_fmt yuv420p -f yuv4mpegpipe - | tools/out/theora_enc out.ogv [quality] [keyint]
 *       [forced keyframes, e.g. 199 or 64,199]
 *
 * quality 0..63 (default 48), keyframe interval in frames (default 64), and frames (0-based) that must be
 * keyframes besides: before such a frame the forced keyframe distance is set to the frames since the last keyframe
 * (TH_ENCCTL_SET_KEYFRAME_FREQUENCY_FORCE; it may change mid-stream, up to 1 << granule shift), then set back, so
 * the regular interval counts on from it. Used to start a still hold on a keyframe (its quality does not change
 * when a later keyframe would land inside it). The picture keeps its size: Theora codes
 * 16 px macroblocks, so the frame is padded to a multiple of 16 by repeating the last row and column, and the
 * picture region is the original size. Deterministic: a fixed stream serial number. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ogg/ogg.h>
#include <theora/theoraenc.h>

static int read_line(FILE *f, char *buf, int n) {
	int i = 0, c;
	while ((c = fgetc(f)) != EOF) {
		if (c == '\n') {
			buf[i] = 0;
			return 1;
		}
		if (i < n - 1)
			buf[i++] = (char)c;
	}
	buf[i] = 0;
	return 0;
}

static void write_page(FILE *out, const ogg_page *og) {
	fwrite(og->header, 1, og->header_len, out);
	fwrite(og->body, 1, og->body_len, out);
}

static int ilog(unsigned v) {
	int r = 0;
	while (v) {
		r++;
		v >>= 1;
	}
	return r;
}

/* copy a w x h plane into a fw x fh one, repeating the last column and row into the padding */
static void pad_plane(unsigned char *dst, int fw, int fh, const unsigned char *src, int w, int h) {
	for (int y = 0; y < h; y++) {
		memcpy(dst + (size_t)y * fw, src + (size_t)y * w, w);
		memset(dst + (size_t)y * fw + w, src[(size_t)y * w + w - 1], fw - w);
	}
	for (int y = h; y < fh; y++)
		memcpy(dst + (size_t)y * fw, dst + (size_t)(h - 1) * fw, fw);
}

int main(int argc, char **argv) {
	if (argc < 2) {
		fprintf(stderr, "usage: theora_enc out.ogv [quality 0-63 (48)] [keyframe interval (64)] [forced keyframes "
						"n,n,...] < in.y4m\n");
		return 2;
	}
	int quality = argc > 2 ? atoi(argv[2]) : 48;
	int keyint = argc > 3 ? atoi(argv[3]) : 64;
	int forced[64], n_forced = 0;
	if (argc > 4) {
		for (char *t = strtok(argv[4], ","); t && n_forced < 64; t = strtok(NULL, ","))
			forced[n_forced++] = atoi(t);
	}
	if (quality < 0 || quality > 63 || keyint < 1) {
		fprintf(stderr, "theora_enc: quality 0..63, keyframe interval >= 1\n");
		return 2;
	}
	char line[1024];
	if (!read_line(stdin, line, sizeof line) || strncmp(line, "YUV4MPEG2 ", 10)) {
		fprintf(stderr, "theora_enc: stdin is not a YUV4MPEG2 stream\n");
		return 1;
	}
	int w = 0, h = 0, fn = 24, fd = 1, an = 1, ad = 1;
	char cs[32] = "420";
	for (char *t = strtok(line + 10, " "); t; t = strtok(NULL, " ")) {
		switch (t[0]) {
			case 'W': w = atoi(t + 1); break;
			case 'H': h = atoi(t + 1); break;
			case 'F': sscanf(t + 1, "%d:%d", &fn, &fd); break;
			case 'A': sscanf(t + 1, "%d:%d", &an, &ad); break;
			case 'C': strncpy(cs, t + 1, sizeof cs - 1); break;
		}
	}
	if (strncmp(cs, "420", 3)) {
		fprintf(stderr, "theora_enc: needs 4:2:0 input (ffmpeg -pix_fmt yuv420p), got C%s\n", cs);
		return 1;
	}
	if (w <= 0 || h <= 0 || (w & 1) || (h & 1) || fn <= 0 || fd <= 0) {
		fprintf(stderr, "theora_enc: bad stream header (%dx%d, %d:%d fps)\n", w, h, fn, fd);
		return 1;
	}
	if (an <= 0 || ad <= 0)
		an = ad = 1;
	int fw = (w + 15) & ~15, fh = (h + 15) & ~15;
	int cw = w / 2, ch = h / 2, fcw = fw / 2, fch = fh / 2;

	th_info ti;
	th_info_init(&ti);
	ti.frame_width = fw;
	ti.frame_height = fh;
	ti.pic_width = w;
	ti.pic_height = h;
	ti.pic_x = 0;
	ti.pic_y = 0;
	ti.fps_numerator = fn;
	ti.fps_denominator = fd;
	ti.aspect_numerator = an;
	ti.aspect_denominator = ad;
	ti.colorspace = TH_CS_UNSPECIFIED;
	ti.pixel_fmt = TH_PF_420;
	ti.target_bitrate = 0;
	ti.quality = quality;
	ti.keyframe_granule_shift = ilog(keyint - 1);
	th_enc_ctx *td = th_encode_alloc(&ti);
	th_info_clear(&ti);
	if (!td) {
		fprintf(stderr, "theora_enc: th_encode_alloc failed\n");
		return 1;
	}
	th_encode_ctl(td, TH_ENCCTL_SET_KEYFRAME_FREQUENCY_FORCE, &keyint, sizeof keyint);

	FILE *out = fopen(argv[1], "wb");
	if (!out) {
		perror(argv[1]);
		return 1;
	}
	ogg_stream_state to;
	ogg_stream_init(&to, 0x4d616e6f);
	th_comment tc;
	th_comment_init(&tc);
	th_comment_add_tag(&tc, "ENCODER", "mano-godot tools/video/theora_enc");
	ogg_packet op;
	ogg_page og;
	/* the first header packet gets a page of its own, then the other two */
	if (th_encode_flushheader(td, &tc, &op) <= 0) {
		fprintf(stderr, "theora_enc: header failed\n");
		return 1;
	}
	ogg_stream_packetin(&to, &op);
	if (ogg_stream_pageout(&to, &og) != 1) {
		fprintf(stderr, "theora_enc: header page failed\n");
		return 1;
	}
	write_page(out, &og);
	for (;;) {
		int r = th_encode_flushheader(td, &tc, &op);
		if (r < 0) {
			fprintf(stderr, "theora_enc: header failed\n");
			return 1;
		}
		if (r == 0)
			break;
		ogg_stream_packetin(&to, &op);
	}
	while (ogg_stream_flush(&to, &og))
		write_page(out, &og);

	size_t fsize = (size_t)w * h + 2 * (size_t)cw * ch;
	unsigned char *raw = malloc(fsize);
	unsigned char *buf[2][3];
	for (int b = 0; b < 2; b++) {
		buf[b][0] = malloc((size_t)fw * fh);
		buf[b][1] = malloc((size_t)fcw * fch);
		buf[b][2] = malloc((size_t)fcw * fch);
	}
	/* one frame of look-ahead: the encoder must be told which frame is the last */
	int cur = 0, frames = 0;
	int have = 0;
	int last_key = 0, keys[256], n_keys = 0;
	for (int pass = 0;; pass++) {
		int b = pass == 0 ? 0 : 1 - cur;
		int got = read_line(stdin, line, sizeof line) && !strncmp(line, "FRAME", 5) && fread(raw, 1, fsize, stdin) == fsize;
		if (got) {
			pad_plane(buf[b][0], fw, fh, raw, w, h);
			pad_plane(buf[b][1], fcw, fch, raw + (size_t)w * h, cw, ch);
			pad_plane(buf[b][2], fcw, fch, raw + (size_t)w * h + (size_t)cw * ch, cw, ch);
		}
		if (pass == 0) {
			have = got;
			cur = 0;
			if (!have)
				break;
			continue;
		}
		th_ycbcr_buffer yb;
		yb[0].width = fw; yb[0].height = fh; yb[0].stride = fw; yb[0].data = buf[cur][0];
		yb[1].width = fcw; yb[1].height = fch; yb[1].stride = fcw; yb[1].data = buf[cur][1];
		yb[2].width = fcw; yb[2].height = fch; yb[2].stride = fcw; yb[2].data = buf[cur][2];
		int force = 0;
		for (int f = 0; f < n_forced; f++)
			if (forced[f] == frames && frames > last_key)
				force = 1;
		if (force) {
			int d = frames - last_key;
			th_encode_ctl(td, TH_ENCCTL_SET_KEYFRAME_FREQUENCY_FORCE, &d, sizeof d);
		}
		if (th_encode_ycbcr_in(td, yb)) {
			fprintf(stderr, "theora_enc: encode failed at frame %d\n", frames);
			return 1;
		}
		if (force)
			th_encode_ctl(td, TH_ENCCTL_SET_KEYFRAME_FREQUENCY_FORCE, &keyint, sizeof keyint);
		int r;
		while ((r = th_encode_packetout(td, !got, &op)) > 0) {
			if (op.bytes > 0 && th_packet_iskeyframe(&op) == 1) {
				last_key = frames;
				if (n_keys < 256)
					keys[n_keys++] = frames;
			}
			ogg_stream_packetin(&to, &op);
			while (ogg_stream_pageout(&to, &og))
				write_page(out, &og);
		}
		frames++;
		if (!got)
			break;
		cur = b;
	}
	while (ogg_stream_flush(&to, &og))
		write_page(out, &og);
	fclose(out);
	th_encode_free(td);
	th_comment_clear(&tc);
	ogg_stream_clear(&to);
	fprintf(stderr, "theora_enc: %d frames, %dx%d, %d/%d fps, quality %d, keyframe every %d -> %s\n", frames, w, h, fn, fd,
			quality, keyint, argv[1]);
	fprintf(stderr, "theora_enc: keyframes at");
	for (int k = 0; k < n_keys; k++)
		fprintf(stderr, " %d", keys[k]);
	fprintf(stderr, "\n");
	return frames > 0 ? 0 : 1;
}

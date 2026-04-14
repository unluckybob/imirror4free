# FFmpeg Binaries

MIRANCE uses PyAV (Python FFmpeg wrapper) which includes FFmpeg binaries.

For exact AnyMiro compatibility, the following FFmpeg DLLs are also provided:
- avcodec-60.dll (video codec)
- avformat-60.dll (format/demuxer)
- avutil-58.dll (utilities)
- swresample-4.dll (audio resampling)
- swscale-7.dll (video scaling)

These can be used as fallback if PyAV's bundled FFmpeg has issues.

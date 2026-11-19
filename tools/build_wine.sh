#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
set -euo pipefail
export LC_ALL=C CCACHE_DISABLE=1
cd /work/wine
perl tools/make_requests
perl tools/make_specfiles
autoreconf -fiv

export CC=x86_64-linux-gnu-gcc CXX=x86_64-linux-gnu-g++
export AR=x86_64-linux-gnu-ar RANLIB=x86_64-linux-gnu-ranlib LD=x86_64-linux-gnu-ld
export RC=x86_64-w64-mingw32-windres WIDL=x86_64-w64-mingw32-widl STRIP=strip
export PKG_CONFIG=x86_64-linux-gnu-pkg-config PKG_CONFIG_PATH=''
export PKG_CONFIG_LIBDIR=/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig
common='-mcmodel=small -march=nocona -mtune=core-avx2 -mfpmath=sse -O2 -fwrapv -fno-strict-aliasing -ggdb -ffunction-sections -fdata-sections -fno-omit-frame-pointer -ffile-prefix-map=/work/wine=. -Wl,--exclude-libs=libstdc++.a -Wno-discarded-qualifiers'
export CFLAGS="$common" CPPFLAGS="$common" CXXFLAGS="-std=c++17 $common"
export CROSSCFLAGS="$common" LDFLAGS='' CROSSLDFLAGS=''

mkdir -p /work/obj-x86_64 /work/artifacts
cd /work/obj-x86_64
/work/wine/configure --host=x86_64-linux-gnu --prefix=/work/dst --libdir=/work/dst/lib \
    --enable-werror --disable-tests --with-mingw=gcc --with-x --with-opengl --with-vulkan \
    --enable-win64 --enable-archs=x86_64
make -j12 __tooldeps__
make -j12 server/wineserver dlls/ntdll/ntdll.so dlls/wow64/x86_64-windows/wow64.dll \
    dlls/winex11.drv/winex11.so programs/explorer/explorer.so
cp server/wineserver dlls/ntdll/ntdll.so dlls/wow64/x86_64-windows/wow64.dll \
    dlls/winex11.drv/winex11.so programs/explorer/explorer.so /work/artifacts/

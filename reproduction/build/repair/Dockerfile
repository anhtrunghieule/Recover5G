# Open5GS e85748e + the orphan-session repair (f12-repair.diff, as published in open5gs issue #5059).
# Built from the cached source tree in r5g/open5gs-build:base; no network access needed.
FROM r5g/open5gs-build:base AS build
COPY f12-repair.diff /tmp/f12-repair.diff
RUN test "$(head -1 /COMMIT)" = e85748ef3d798fa0b4435c80438e81c41bbe5e13 \
 && cd /src/open5gs && patch -p1 --no-backup-if-mismatch < /tmp/f12-repair.diff \
 && echo "patch:f12-repair.diff" >> /COMMIT \
 && nice -n 10 ninja -C build -j6 && ninja -C build install
FROM r5g/open5gs:e85748e
COPY --from=build /opt/open5gs /opt/open5gs
COPY --from=build /COMMIT /COMMIT

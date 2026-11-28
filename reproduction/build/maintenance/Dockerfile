FROM r5g/open5gs-build:base AS build
RUN mkdir -p /deps && cp -a /src/open5gs/subprojects/freeDiameter /src/open5gs/subprojects/prometheus-client-c /deps/ && rm -rf /src/open5gs /opt/open5gs && mkdir -p /src/open5gs
ADD open5gs.tar.gz /tmp/source/
RUN cp -a /tmp/source/open5gs-*/. /src/open5gs/ && cp -a /deps/. /src/open5gs/subprojects/ && cd /src/open5gs && meson setup build --prefix=/opt/open5gs --buildtype=debugoptimized && ninja -C build -j4 && ninja -C build install
FROM r5g/open5gs:e85748e
COPY --from=build /opt/open5gs /opt/open5gs
RUN printf "%s\n" "5378c0698c604bd16e0287eadab069bc51e7fb5f" > /COMMIT

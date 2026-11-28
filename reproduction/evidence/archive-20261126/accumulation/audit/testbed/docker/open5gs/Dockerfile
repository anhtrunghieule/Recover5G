# Open5GS built from source at a pinned commit (arm64-native or amd64).
FROM ubuntu:24.04 AS build
ARG OPEN5GS_COMMIT=e85748ef3d798fa0b4435c80438e81c41bbe5e13
ENV DEBIAN_FRONTEND=noninteractive
ARG UBUNTU_MIRROR=http://free.nchc.org.tw/ubuntu-ports
RUN sed -i "s#http://ports.ubuntu.com/ubuntu-ports#${UBUNTU_MIRROR}#g" /etc/apt/sources.list.d/ubuntu.sources
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-setuptools python3-wheel ninja-build build-essential flex bison git cmake \
    libsctp-dev libgnutls28-dev libgcrypt-dev libssl-dev libmongoc-dev libbson-dev libyaml-dev \
    libnghttp2-dev libmicrohttpd-dev libcurl4-gnutls-dev libnghttp2-dev libtins-dev libtalloc-dev \
    libidn-dev meson ca-certificates pkg-config curl && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /src/open5gs && curl -sfL https://github.com/open5gs/open5gs/archive/${OPEN5GS_COMMIT}.tar.gz | tar xz --strip-components=1 -C /src/open5gs \
    && echo ${OPEN5GS_COMMIT} > /COMMIT
RUN cd /src/open5gs && meson setup build --prefix=/opt/open5gs --buildtype=debugoptimized -Dmetrics_impl=prometheus || meson setup build --prefix=/opt/open5gs --buildtype=debugoptimized
RUN cd /src/open5gs && ninja -C build -j8 && ninja -C build install

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
ARG UBUNTU_MIRROR=http://free.nchc.org.tw/ubuntu-ports
RUN sed -i "s#http://ports.ubuntu.com/ubuntu-ports#${UBUNTU_MIRROR}#g" /etc/apt/sources.list.d/ubuntu.sources
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsctp1 libgnutls30t64 libgcrypt20 libssl3t64 libmongoc-1.0-0t64 libbson-1.0-0t64 libyaml-0-2 \
    libnghttp2-14 libmicrohttpd12t64 libcurl3t64-gnutls libtins4.5 libtalloc2 libidn12 \
    iproute2 iptables iputils-ping net-tools tcpdump procps ca-certificates curl && rm -rf /var/lib/apt/lists/* || \
    (apt-get update && apt-get install -y --no-install-recommends libsctp1 libyaml-0-2 iproute2 iptables iputils-ping net-tools tcpdump procps curl)
COPY --from=build /opt/open5gs /opt/open5gs
COPY --from=build /COMMIT /COMMIT
COPY --from=build /src/open5gs/misc/db/open5gs-dbctl /opt/open5gs/bin/open5gs-dbctl
ENV PATH=/opt/open5gs/bin:$PATH LD_LIBRARY_PATH=/opt/open5gs/lib:/opt/open5gs/lib/aarch64-linux-gnu:/opt/open5gs/lib/x86_64-linux-gnu
WORKDIR /opt/open5gs

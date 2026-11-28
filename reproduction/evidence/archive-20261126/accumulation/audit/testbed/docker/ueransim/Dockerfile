FROM ubuntu:24.04 AS build
ARG UERANSIM_COMMIT=4f45e18f80b0684f7d6e29f1fea0f579e9243d68
ENV DEBIAN_FRONTEND=noninteractive
ARG UBUNTU_MIRROR=http://free.nchc.org.tw/ubuntu-ports
RUN sed -i "s#http://ports.ubuntu.com/ubuntu-ports#${UBUNTU_MIRROR}#g" /etc/apt/sources.list.d/ubuntu.sources
RUN apt-get update && apt-get install -y --no-install-recommends make gcc g++ libsctp-dev lksctp-tools cmake git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /src/ueransim && curl -sfL https://github.com/aligungr/UERANSIM/archive/${UERANSIM_COMMIT}.tar.gz | tar xz --strip-components=1 -C /src/ueransim \
    && echo ${UERANSIM_COMMIT} > /COMMIT && cd /src/ueransim \
    # harness patch: UAC check waits 100 ms for the RRC task; under load NAS requests were dropped and only
    # retransmitted after T3580 (16 s). Raise the wait to 2000 ms (UE-side only; core behaviour unaffected).
    && sed -i 's/LightSync<UacInput, UacOutput>::MakeShared(100, 0/LightSync<UacInput, UacOutput>::MakeShared(2000, 0/' src/ue/nas/mm/access.cpp \
    && grep -q 'MakeShared(2000, 0' src/ue/nas/mm/access.cpp && echo 'uac-wait-2000ms' >> /COMMIT && make -j8

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
ARG UBUNTU_MIRROR=http://free.nchc.org.tw/ubuntu-ports
RUN sed -i "s#http://ports.ubuntu.com/ubuntu-ports#${UBUNTU_MIRROR}#g" /etc/apt/sources.list.d/ubuntu.sources
RUN apt-get update && apt-get install -y --no-install-recommends libsctp1 lksctp-tools iproute2 iputils-ping procps net-tools tcpdump curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/ueransim/build /ueransim
COPY --from=build /src/ueransim/config /ueransim/config-default
COPY --from=build /COMMIT /COMMIT
ENV PATH=/ueransim:$PATH
WORKDIR /ueransim

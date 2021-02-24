FROM ubuntu:20.04

COPY . /azure-capi-cli-extension
WORKDIR /azure-capi-cli-extension

RUN apt-get update && \
    apt-get install --yes --no-install-suggests --no-install-recommends --yes \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        python3 \
        python3-pip \
        python3-venv \
        git \
        && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 4 && \
    python -m pip install --upgrade pip && \
    python -m pip install \
        argcomplete \
        argparse \
        && \
    rm -rf /var/lib/apt/lists/* /root/.cache

# Azure CLI
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $(lsb_release -sc) main" > /etc/apt/sources.list.d/azure-cli.list && \
    apt-get -qq update && \
    apt-get -qq install --yes --no-install-suggests --no-install-recommends \
        azure-cli && \
    rm -rf /var/lib/apt/lists/* /root/.cache

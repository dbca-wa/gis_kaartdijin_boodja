# Prepare the base environment.
ARG IMAGE_TAG
ARG IMAGE_NAME
FROM ghcr.io/dbca-wa/docker-apps-dev:ubuntu_2604_base_python AS builder_base_gis_kaartdijin_boodja
ARG IMAGE_TAG
ARG IMAGE_NAME
RUN echo "Building version: $IMAGE_TAG for $IMAGE_NAME"
ENV CONTAINER_IMAGE_TAG=${IMAGE_TAG}
ENV CONTAINER_IMAGE_NAME=${IMAGE_NAME}
MAINTAINER asi@dbca.wa.gov.au
ENV DEBIAN_FRONTEND=noninteractive
ENV DEBUG=True
ENV TZ=Australia/Perth
ENV PRODUCTION_EMAIL=True
ENV SECRET_KEY="ThisisNotRealKey"
ENV SITE_DOMAIN='dbca.wa.gov.au'
ENV BPAY_ALLOWED=False
ENV VIRTUAL_ENV=/app/venv
ENV PATH=$VIRTUAL_ENV/bin:$PATH

RUN sed 's/archive.ubuntu.com/en.archive.ubuntu.com/g' /etc/apt/sources.list > /etc/apt/sourcesau.list
RUN mv /etc/apt/sourcesau.list /etc/apt/sources.list


RUN apt-get clean
RUN apt-get update
RUN apt-get upgrade -y
# RUN apt-get install --no-install-recommends -y curl wget git libmagic-dev gcc binutils python3 python3-setuptools python3-dev python3-pip tzdata cron gpg-agent
RUN apt-get install --no-install-recommends -y python3-venv
RUN apt-get install --no-install-recommends -y gpg-agent
RUN apt-get install --no-install-recommends -y vim htop
RUN apt-get install --no-install-recommends -y software-properties-common 
 
# ADDED START from bottom
RUN apt-get install --no-install-recommends -y python3-pil
# RUN apt-get install --no-install-recommends -y postgis 
# ADDED END from bottom

# Install GDAL
# RUN add-apt-repository ppa:ubuntugis/ubuntugis-unstable
# RUN apt update
RUN apt-get install --no-install-recommends -y gdal-bin python3-gdal
RUN apt-get install --no-install-recommends -y libgdal-dev build-essential

RUN update-ca-certificates
# install node 18
# RUN touch install_node.sh
# RUN curl -fsSL https://deb.nodesource.com/setup_18.x -o install_node.sh
# RUN chmod +x install_node.sh && ./install_node.sh
# RUN apt-get install -y nodejs
# RUN ln -s /usr/bin/python3.10 /usr/bin/python
#RUN pip install --upgrade pip
#RUN wget -O /tmp/GDAL-3.8.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl https://github.com/girder/large_image_wheels/raw/wheelhouse/GDAL-3.8.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl#sha256=e2fe6cfbab02d535bc52c77cdbe1e860304347f16d30a4708dc342a231412c57
#RUN pip install /tmp/GDAL-3.8.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
# Install Python libs using pyproject.toml and poetry.lock
FROM builder_base_gis_kaartdijin_boodja AS python_libs_gis_kaartdijin_boodja

RUN groupadd -g 5000 oim
RUN useradd -g 5000 -u 5000 oim -s /bin/bash -d /app
RUN usermod -a -G sudo oim
RUN mkdir /app 
RUN chown -R oim.oim /app

COPY timezone /etc/timezone
ENV TZ=Australia/Perth
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Default Scripts
RUN wget https://raw.githubusercontent.com/dbca-wa/wagov_utils/main/wagov_utils/bin/default_script_installer.sh -O /tmp/default_script_installer.sh
RUN chmod 755 /tmp/default_script_installer.sh
RUN /tmp/default_script_installer.sh

COPY startup.sh /
RUN chmod 755 /startup.sh

WORKDIR /app
USER oim
RUN python3 -m venv $VIRTUAL_ENV
RUN git config --global --add safe.directory /app
COPY requirements.txt ./

# --- GDAL SETUP START ---
# 1. Provide the compiler with explicit paths to the GDAL C++ header files.
# In newer Ubuntu 26.04 / Python 3.14+ environments, the build system often fails 
# to automatically locate 'gdal.h'. These environment variables ensure the Python 
# wrapper can find the underlying C++ headers required for compilation.
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# 2. Synchronize and pre-install the Python GDAL package with the system library version.
# GDAL's Python bindings are extremely sensitive to version mismatches with the 
# system's 'libgdal'. By detecting the version via 'gdal-config' and installing it 
# separately, we avoid the "Failed to build GDAL" errors that occur when pip tries 
# to compile an incompatible version from 'requirements.txt'.
RUN export GDAL_VERSION=$(gdal-config --version) && \
    pip install --upgrade pip setuptools wheel && \
    pip install "GDAL==${GDAL_VERSION}.*"
# --- GDAL SETUP END ---

RUN pip install -r requirements.txt

# Install the project (ensure that frontend projects have been built prior to this step).
FROM python_libs_gis_kaartdijin_boodja

COPY --chown=oim:oim gunicorn.ini manage.py ./
RUN touch /app/.env
COPY .git ./.git
COPY --chown=oim:oim govapp ./govapp
COPY python-cron ./
#RUN pip install GDAL==3.8.4
RUN python manage.py collectstatic --noinput

# Cleanup
USER root
RUN wget https://raw.githubusercontent.com/dbca-wa/wagov_utils/refs/heads/main/wagov_utils/bin/package_cleanup_2604.sh -O /tmp/package_cleanup_2604.sh
RUN chmod 755 /tmp/package_cleanup_2604.sh
RUN /tmp/package_cleanup_2604.sh
USER oim

EXPOSE 8080
HEALTHCHECK --interval=1m --timeout=5s --start-period=10s --retries=3 CMD ["wget", "-q", "-O", "-", "http://localhost:8080/"]
CMD ["/startup.sh"]
LABEL org.opencontainers.image.source="https://github.com/dbca-wa/gis_kaartdijin_boodja"

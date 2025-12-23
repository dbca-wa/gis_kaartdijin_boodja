# Prepare the base environment.
FROM ubuntu:24.04 AS builder_base_gis_kaartdijin_boodja
MAINTAINER asi@dbca.wa.gov.au
ENV DEBIAN_FRONTEND=noninteractive
ENV DEBUG=True
ENV TZ=Australia/Perth
ENV PRODUCTION_EMAIL=True
ENV SECRET_KEY="ThisisNotRealKey"
ENV SITE_DOMAIN='dbca.wa.gov.au'
ENV BPAY_ALLOWED=False

RUN sed 's/archive.ubuntu.com/en.archive.ubuntu.com/g' /etc/apt/sources.list > /etc/apt/sourcesau.list
RUN mv /etc/apt/sourcesau.list /etc/apt/sources.list


RUN apt-get clean
RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install --no-install-recommends -y curl wget git libmagic-dev gcc binutils python3 python3-setuptools python3-dev python3-pip tzdata cron gpg-agent
RUN apt-get install --no-install-recommends -y libpq-dev patch virtualenv
RUN apt-get install --no-install-recommends -y postgresql-client mtr systemd
RUN apt-get install --no-install-recommends -y vim postgresql-client ssh htop
RUN apt-get install --no-install-recommends -y software-properties-common 
 
# ADDED START from bottom
RUN apt-get install --no-install-recommends -y python3-pil
RUN apt-get install --no-install-recommends -y postgis 
# ADDED END from bottom

RUN add-apt-repository ppa:deadsnakes/ppa -y
RUN apt update
RUN apt-get install --no-install-recommends -y  python3.10

# Install GDAL
RUN add-apt-repository ppa:ubuntugis/ubuntugis-unstable
RUN apt update
RUN apt-get install --no-install-recommends -y gdal-bin python3-gdal
RUN apt-get install --no-install-recommends -y libgdal-dev build-essential

RUN update-ca-certificates
# install node 18
RUN touch install_node.sh
RUN curl -fsSL https://deb.nodesource.com/setup_18.x -o install_node.sh
RUN chmod +x install_node.sh && ./install_node.sh
RUN apt-get install -y nodejs
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
#ENV POETRY_VERSION=1.3.2
RUN virtualenv /app/venv
ENV PATH=/app/venv/bin:$PATH
RUN git config --global --add safe.directory /app
# RUN curl -sSL https://install.python-poetry.org | python -
#RUN ln -s /root/.local/bin/poetry /usr/bin/poetry
#RUN poetry config virtualenvs.create false
#COPY pyproject.toml poetry.lock ./
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt
#RUN pip install "poetry==$POETRY_VERSION"
#RUN poetry install 

# Install the project (ensure that frontend projects have been built prior to this step).
FROM python_libs_gis_kaartdijin_boodja


COPY --chown=oim:oim gunicorn.ini manage.py ./
RUN touch /app/.env
COPY .git ./.git
COPY --chown=oim:oim govapp ./govapp
COPY python-cron ./
#RUN pip install GDAL==3.8.4
RUN python manage.py collectstatic --noinput

USER root
RUN rm -rf /var/lib/{apt,dpkg,cache,log}/ /tmp/* /var/tmp/*
USER oim

EXPOSE 8080
HEALTHCHECK --interval=1m --timeout=5s --start-period=10s --retries=3 CMD ["wget", "-q", "-O", "-", "http://localhost:8080/"]
CMD ["/startup.sh"]
LABEL org.opencontainers.image.source="https://github.com/dbca-wa/gis_kaartdijin_boodja"

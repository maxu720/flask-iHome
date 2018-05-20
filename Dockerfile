FROM ubuntu:16.04

RUN apt-get update
RUN apt-get install -y curl
RUN apt-get install -y python-dev
RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
RUN python get-pip.py
RUN apt-get install -y libmysqlclient-dev
RUN apt-get install -y gcc

COPY . /data
RUN pip install -r /data/requirements.txt 

RUN mkdir -p /logs
RUN touch /logs/log

CMD python /data/manage.py runserver






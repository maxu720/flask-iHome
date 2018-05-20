# flask-iHome

docker build -t test .

docker run -ti --rm test /bin/bash
docker run -ti --rm -p 5000:5000 test

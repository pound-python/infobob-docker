FROM golang:alpine
RUN apk --no-cache add git
RUN go get -u \
    github.com/docker/docker/client \
    github.com/joho/godotenv \
    gopkg.in/go-playground/webhooks.v5/github
ADD . /go/src/github.com/pound-python/infobob-docker/webhooks
RUN go install github.com/pound-python/infobob-docker/webhooks

FROM alpine
COPY --from=0 /go/bin/webhooks /usr/local/bin/infobob-webhooks
ENTRYPOINT ["/usr/local/bin/infobob-webhooks"]
EXPOSE 3000

FROM --platform=$BUILDPLATFORM golang:1.26-alpine AS build

ARG TARGETOS
ARG TARGETARCH

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o /chatgpt2api .


FROM alpine:3.22 AS app

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

COPY --from=build /chatgpt2api ./
COPY web ./web
COPY VERSION ./
COPY config.example.yaml ./config.yaml

ENV PORT=80
EXPOSE 80

CMD ["./chatgpt2api"]

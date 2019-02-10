package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/mount"
	"github.com/docker/docker/client"
	"github.com/joho/godotenv"
	"gopkg.in/go-playground/webhooks.v5/docker"
	"gopkg.in/go-playground/webhooks.v5/github"
)

type deployParams struct {
	branch      string
	containerCh chan container.ContainerCreateCreatedBody
}

func processDeploys(deploys chan deployParams) {
	cli, err := client.NewClientWithOpts(client.FromEnv)
	if err != nil {
		log.Panicf("error making docker client: %v", err)
	}
	ctx := context.Background()
	cli.NegotiateAPIVersion(ctx)

	for deploy := range deploys {
		log.Printf("doing a deploy: %+v", deploy)

		resp, err := cli.ContainerCreate(ctx, &container.Config{
			Image: "poundpython/infobob-docker-deploy",
			Cmd:   []string{"-b", deploy.branch, "deploy"},
			Labels: map[string]string{
				"org.pound-python.infobob.created-by": "webhooks-golang",
			},
		}, &container.HostConfig{
			AutoRemove: false,
			Mounts: []mount.Mount{
				{
					Type:     mount.TypeBind,
					Source:   "/var/lib/infobob-gnupg",
					Target:   "/run/gnupg",
					ReadOnly: true,
				},
				{
					Type:   mount.TypeBind,
					Source: "/var/run/docker.sock",
					Target: "/var/run/docker.sock",
				},
				{
					Type:   mount.TypeTmpfs,
					Target: "/tmp",
				},
			},
		}, nil, "")
		if err != nil {
			log.Panicf("error making docker container: %v", err)
		}
		log.Printf("docker container created: %+v", resp)
		deploy.containerCh <- resp

		if err := cli.ContainerStart(ctx, resp.ID, types.ContainerStartOptions{}); err != nil {
			log.Panicf("error starting docker container: %v", err)
		}

		statusCh, errCh := cli.ContainerWait(ctx, resp.ID, container.WaitConditionNotRunning)
		select {
		case err := <-errCh:
			if err != nil {
				log.Panicf("error waiting for docker container: %v", err)
			}
		case status := <-statusCh:
			log.Printf("docker container finished: %+v", status)
		}
	}
}

func main() {
	for _, envfile := range os.Args[1:] {
		if err := godotenv.Load(envfile); err != nil {
			log.Fatalf("error loading .env file %v: %v", envfile, err)
		}
	}

	spawnCh := make(chan deployParams)
	go processDeploys(spawnCh)

	githubHook, err := github.New(github.Options.Secret(os.Getenv("GITHUB_SECRET")))
	if err != nil {
		log.Fatalf("error making github hook: %v", err)
	}
	http.HandleFunc("/webhooks/github", func(w http.ResponseWriter, r *http.Request) {
		log.Printf("req: %+v", r)
		payload, err := githubHook.Parse(r, github.PingEvent, github.ReleaseEvent, github.PullRequestEvent)
		if err != nil {
			log.Printf("err: %+v", err)
		} else {
			log.Printf("ok: %+v", payload)
		}
	})

	dockerHook, err := docker.New()
	if err != nil {
		log.Fatalf("error making docker hook: %v", err)
	}
	dockerHookPath := fmt.Sprintf("/webhooks/docker/%s", os.Getenv("DOCKER_HOOK_SECRET"))
	http.HandleFunc(dockerHookPath, func(w http.ResponseWriter, r *http.Request) {
		log.Printf("req: %+v", r)
		payload, err := dockerHook.Parse(r)
		if err != nil {
			log.Printf("err: %+v", err)
		} else {
			log.Printf("ok: %+v", payload)
		}
	})

	generalHookPath := fmt.Sprintf("/webhooks/general/%s", os.Getenv("GENERAL_HOOK_SECRET"))
	http.HandleFunc(generalHookPath, func(w http.ResponseWriter, r *http.Request) {
		log.Printf("req: %+v", r)
		containerCh := make(chan container.ContainerCreateCreatedBody)
		spawnCh <- deployParams{
			branch:      "testing",
			containerCh: containerCh,
		}
		container := <-containerCh

		js, err := json.Marshal(container)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write(js)
	})

	log.Print("starting server")
	http.ListenAndServe(":3000", nil)
}

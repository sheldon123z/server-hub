export interface Container {
  Names: string
  Image: string
  State: string
  Status: string
  Ports: string
  Created: string
}

export interface DockerImage {
  Repository: string
  Tag: string
  ID: string
  Size: string
  Created: string
}

export interface ComposeStack {
  name: string
  display_name: string
  path: string
  services: number
  running: number
}

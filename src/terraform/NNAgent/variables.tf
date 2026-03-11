variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "nn-agent"
}

variable "lambda_function_name" {
  type    = string
  default = "nn-agent-pricer"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "lambda_timeout" {
  type    = number
  default = 120
}

variable "lambda_memory_size" {
  type    = number
  default = 3008
}

variable "log_retention_in_days" {
  type    = number
  default = 7
}

variable "docker_executable" {
  type    = string
  default = "docker"
}

variable "aws_cli_executable" {
  type    = string
  default = "aws"
}

variable "docker_platform" {
  type    = string
  default = "linux/amd64"
}

variable "auto_build_image" {
  type    = bool
  default = true
}

variable "nn_weights_drive_folder_url" {
  type    = string
  default = "https://drive.google.com/drive/folders/1uq5C9edPIZ1973dArZiEO-VE13F7m8MK?usp=drive_link"
}

variable "tags" {
  type    = map(string)
  default = {}
}

provider "aws" {
  region = "eu-west-1"
}

provider "aws" {
  alias  = "virginia"
  region = "us-east-1"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

module "frontend" {
  source = "../../application/tirociniowebsite"
  bucket_name = var.bucket_name
  env_name=var.env_name
  domain_name=var.domain_name
}
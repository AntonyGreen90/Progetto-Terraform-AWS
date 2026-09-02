# FARGATE SERVERLESS LAUNCHER

resource "aws_ecr_repository" "project_app" { # risorsa ECR (Elastic Container Repo) per pushare l'immagine creata con Dockerfile
  name = "project-app"

  image_scanning_configuration {
    scan_on_push = true
  }

  image_tag_mutability = "MUTABLE"
}

resource "aws_ecr_lifecycle_policy" "repo_policy" {
  repository = aws_ecr_repository.project_app.name

  policy = <<EOF
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep just 2 tagged images maximum pls",
      "selection": {
        "tagStatus": "tagged",
        "tagPrefixList": ["v"],
        "countType": "imageCountMoreThan",
        "countNumber": 2
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
EOF
}

resource "aws_ecs_cluster" "cluster" {
  name = "tirocinioeps-ecs-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "cluster" {
  cluster_name = aws_ecs_cluster.cluster.name

  capacity_providers = ["FARGATE_SPOT", "FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
  }
}

module "ecs-fargate" {
  source = "umotif-public/ecs-fargate/aws"
  version = "8.2.0"

  name_prefix        = "ecs-fargate-tirocinioeps"
  vpc_id             = data.aws_vpc.default.id
  private_subnet_ids = data.aws_subnets.default.ids

  cluster_id         = aws_ecs_cluster.cluster.id

  task_container_image   = "${aws_ecr_repository.project_app.repository_url}:latest"
  task_definition_cpu    = 256
  task_definition_memory = 512

  task_container_port             = 5000
  task_container_assign_public_ip = true

  target_groups = [
    {
      target_group_name = "tg-fargate-example"
      container_name    = "ecs-fargate-tirocinioeps"
      container_port    = 5000
    }
  ]

  task_container_environment = {
      REDIS_URL = "redis://${aws_elasticache_replication_group.valkey.primary_endpoint_address}:6379/0"
      # questo fa si che il cluster repository dei container prenda come indirizzo per la cache l'indirizzo di valkey
  }

  health_check = {
    port = "traffic-port"
    path = "/"
  }

  tags = {
    Environment = "dev"
    Project = "tirocinioepsilo"
  }
}

module "ecs-celery" {
  source = "umotif-public/ecs-fargate/aws"
  version = "8.2.0"

  name_prefix        = "ecs-celery-tirocinioeps"
  vpc_id             = data.aws_vpc.default.id
  private_subnet_ids = data.aws_subnets.default.ids

  cluster_id         = aws_ecs_cluster.cluster.id

  task_container_image   = "${aws_ecr_repository.project_app.repository_url}:latest"
  task_container_assign_public_ip = true
  task_definition_cpu    = 256
  task_definition_memory = 512

  task_container_command = [
  "celery",
  "-A",
  "app.celery",
  "worker",
  "--loglevel=info"
]

  load_balanced = false

  task_container_environment = {
    REDIS_URL = "redis://${aws_elasticache_replication_group.valkey.primary_endpoint_address}:6379/0"
    BUCKET_NAME = aws_s3_bucket.reportsbucket.bucket
  }

  tags = {
    Environment = "dev"
    Project = "tirocinioepsilo"
  }
}

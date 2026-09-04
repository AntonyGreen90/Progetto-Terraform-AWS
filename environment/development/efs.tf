# database condiviso tra Flask, Celery Worker e S3

resource "aws_efs_file_system" "sqlite" {
  creation_token = "tirocinioeps-sqlite"

  tags = {
    Name        = "tirocinioeps-sqlite"
    Environment = "production"
    Project     = "tirocinioepsilo"
  }
}

resource "aws_efs_access_point" "sqlite" {
  file_system_id = aws_efs_file_system.sqlite.id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/data"

    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "0755"
    }
  }

  tags = {
    Name    = "tirocinioeps-sqlite-access-point"
    Project = "tirocinioepsilo"
  }
}

resource "aws_security_group" "efs" {
  name        = "efs-sg"
  description = "Security Group per EFS"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [
      module.ecs-fargate.service_sg_id,
      module.ecs-celery.service_sg_id
    ]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_efs_mount_target" "sqlite" {
  for_each = toset(data.aws_subnets.default.ids)

  file_system_id  = aws_efs_file_system.sqlite.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}
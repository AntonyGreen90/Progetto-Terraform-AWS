# APPLICATION LOAD BALANCER FOR FARGATE MODULE DEPENDENCIES

resource "aws_security_group" "alb" {
  name        = "alb-sg"
  description = "Security Group per ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "alb-sg"
  }
}

resource "aws_lb" "fargate" {
  name               = "alb-fargate"
  load_balancer_type = "application"
  internal           = false

  security_groups = [
    aws_security_group.alb.id
  ]

  subnets = data.aws_subnets.default.ids

  tags = {
    Name = "alb-fargate"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.fargate.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "forward"

    target_group_arn = module.ecs-fargate.target_group_arn[0]
  }
}

# RISORSA PER PERMETTERE ALLA RISORSA ECS DI ACCETTARE CONNESSIONE DALL'ALB SOLO SULLA PORTA 5000
resource "aws_security_group_rule" "ecs_from_alb" {
  type                     = "ingress"
  security_group_id        = module.ecs-fargate.service_sg_id
  source_security_group_id = aws_security_group.alb.id

  from_port = 5000
  to_port   = 5000
  protocol  = "tcp"

  description = "Allow ALB to reach ECS container"
}
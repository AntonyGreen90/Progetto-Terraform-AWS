module "acm" {
  source = "terraform-aws-modules/acm/aws"
  version= "6.3.0"

  providers = {
    aws = aws.us-east-1
  }

  domain_name = "${var.domain_name}"

  validation_method = "DNS"

  create_route53_records=false

  wait_for_validation = false

  tags = {
    Name = "${var.domain_name}"
  }
}
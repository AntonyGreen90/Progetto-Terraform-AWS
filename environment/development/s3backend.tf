# AWS S3 Storage for reports instead of Minio

resource "random_id" "bucket_suffix" {
  byte_length = 4  # Generates 8 hex characters
}

resource "aws_s3_bucket" "reportsbucket" {
  bucket = "${var.bucket_name_backend}-${random_id.bucket_suffix.hex}"

  tags = {
    Environment = "production"
    Project     = "tirocinioepsilo"
  }
}

resource "aws_iam_role_policy" "celery_s3" {
  name = "celery-s3-reports"
  role = module.ecs-celery.task_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.reportsbucket.arn}/*"
      }
    ]
  })
}
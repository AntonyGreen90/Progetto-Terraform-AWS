resource "random_id" "bucket_suffix" {
  byte_length = 4  # Generates 8 hex characters
}

resource "aws_s3_bucket" "websitebucket" {
  bucket = "${var.bucket_name}-${random_id.bucket_suffix.hex}"
  tags = {
    Name        = "${var.bucket_name}-${random_id.bucket_suffix.hex}"
    Environment = "dev"
  }
}

data "aws_iam_policy_document" "origin_bucket_policy" {
  statement {
    sid = "AllowCloudFrontServicePrincipalReadWrite"
    effect = "Allow"
    
    principals {
      type= "Service"
      identifiers =["cloudfront.amazonaws.com"]
    }

    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.websitebucket.arn}/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.s3_distribution.arn]
    }
  }
}

resource "aws_s3_bucket_public_access_block" "s3publicblock" {
  bucket = "${var.bucket_name}-${random_id.bucket_suffix.hex}"

  block_public_acls   = true
  block_public_policy = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "cloudfront_access" {
  bucket = "${var.bucket_name}-${random_id.bucket_suffix.hex}"
  policy = data.aws_iam_policy_document.origin_bucket_policy.json
}

resource "aws_s3_bucket_website_configuration" "webconf" {
  bucket = "${var.bucket_name}-${random_id.bucket_suffix.hex}"

  index_document {
    suffix = "index.html"
  }
}

resource "aws_s3_object" "index" {
  bucket = "${var.bucket_name}-${random_id.bucket_suffix.hex}"
  key    = "index.html"
  source = "${path.module}/index.html"
  content_type = "text/html"
}
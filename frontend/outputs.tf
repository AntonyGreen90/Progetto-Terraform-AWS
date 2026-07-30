output "bucket_id" {
    description = "Id of the created bucket"
    value= aws_s3_bucket.websitebucket.id
}

output "website_endpoint" {
    description = "Endpoint to visit bucket website"
    value= aws_s3_bucket_website_configuration.webconf.website_endpoint
}
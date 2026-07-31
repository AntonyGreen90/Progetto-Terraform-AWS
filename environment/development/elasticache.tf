resource "aws_security_group" "valkey" {

  name   = "valkey-sg"

  vpc_id = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "valkeysec" {

  security_group_id = aws_security_group.valkey.id

  from_port = 6379
  to_port   = 6379

  ip_protocol = "tcp"

  cidr_ipv4 = data.aws_vpc.default.cidr_block
}

resource "aws_elasticache_subnet_group" "valkeysub" {

  name = "valkey-subnet-group"

  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_elasticache_replication_group" "valkey" {

  replication_group_id = "my-valkey"

  description = "Valkey for Flask"

  engine       = "valkey"
  engine_version = "8.1"

  node_type = "cache.t4g.micro"

  num_cache_clusters = 1

  port = 6379

  subnet_group_name = aws_elasticache_subnet_group.valkeysub.name

  security_group_ids = [
    aws_security_group.valkey.id
  ]

  automatic_failover_enabled = false
}

# QUESTO SAREBBE VECCHIO?
# resource "aws_elasticache_cluster" "example" {
#   cluster_id           = "cluster-example"
#   engine               = "valkey"              
#   engine_version       = "7.2"                
#   parameter_group_name = "default.valkey7"     
#   node_type            = "cache.t4g.micro"    
#   num_cache_nodes      = 1
#   port                 = 6379
# }
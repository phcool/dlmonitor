source ./.env
sudo -u postgres psql -c "create user $DATABASE_USER createdb createrole password '$DATABASE_PASSWD';"
sudo -u postgres psql -c "create database dlmonitor owner $DATABASE_USER;"

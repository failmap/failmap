Test that require a more complete environment than mere unit tests would. Skipped during normal test.

To run these tests succesfully a (complete) runtime environment needs to be available (ie: database, broker, etc). For development this environment can be created using Docker (see main README.md for using Docker composer to start runtime environment), TLDR: `docker-compose up -d`. During CI testing an environment is created in the CI instance.

Since integrationtest run against runtime components these tests are allowed to take more time (eg: wait for responses using sleep) compared to unit tests that can for example work around this using mocks.

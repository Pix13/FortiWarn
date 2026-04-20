# FortiWarn

FortiWarn is a python daemon that will query regularly a fortinet HA pair to check if the internet connexion of a SDWAN Pair have switched to the backup connexion
The name of the main and backup interfaces are to be provided in a env file, along with all the credentials for the Fortinet access.
If a change is detected, the daemon sends an email ( taken from a template ) to a specific address.

## Code Style

- Use Python3 syntax in all files

## Architecture

- Follow MVC pattern
- Keep components under 200 lines
- Use dependency injection

## Testing

- Write unit tests for all business logic
- Maintain >80% code coverage
- Use pytest for testing

## Security

- Never commit API keys or secrets
- Validate all user inputs


# Plan: remote sudo repository access

1. Define a shared effective remote Borg command from repository and SSH
   connection settings.
2. Route Borg 1 and Borg 2 maintenance and archive operations through it.
3. Make remote-direct create use non-interactive sudo with a root home.
4. Add focused unit coverage and run backend validation.

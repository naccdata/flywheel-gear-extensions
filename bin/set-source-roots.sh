#!/bin/sh
ROOTS=$(pants roots --roots-sep=' ')
python3 -c "print('PYTHONPATH=\"./' + ':./'.join('''${ROOTS}'''.split('\n')) + ':\$PYTHONPATH\"')" > .env

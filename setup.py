#!/usr/bin/env python
from setuptools import setup

setup(name='syncdir',
      version='0.1',
      description='Yet another rsync-like program written in Python',
      url='https://github.com/euske/syncdir',
      author='Yusuke Shinyama',
      author_email='yusuke@shinyama.jp',
      license='MIT',
      packages=[],
      install_requires=['paramiko'],
      scripts=['syncdir3.py'],
      classifiers=[
          'Development Status :: 4 - Beta',
          'Environment :: Console',
          'License :: OSI Approved :: MIT License',
          'Topic :: Utilities',
      ],
)

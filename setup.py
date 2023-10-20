from setuptools import setup, find_packages

setup(
    name='pyhkc',
    version='0.1',  # start with a small number, increment as you make changes
    packages=find_packages(),
    install_requires=open('requirements.txt').readlines(),
    # Metadata
    author='Jason Madigan',
    author_email='jason@jasonmadigan.com',
    description='A Python client for HKC SecureComm API',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/jasonmadigan/pyhkc',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
    ],
)
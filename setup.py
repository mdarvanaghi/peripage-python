from setuptools import setup, find_packages

setup(
    name = 'peripage',
    packages = find_packages(include=['peripage', 'peripage.*']),
    package_data = {
        'peripage': ['fonts/*.ttf', 'fonts/LICENSE.txt'],
    },
    include_package_data = True,
    version = '1.2',
    license='MIT',
    description = 'Utility for printing on Peripage printers via bluetooth',
    author = 'bitrate16',
    author_email = 'bitrate16@gmail.com',
    url = 'https://github.com/bitrate16/peripage-python',
    keywords = ['PERIPAGE', 'BLUETOOTH', 'THERMAL PRINTER', 'PRINTER'],
    install_requires=[
        'Pillow>=8.2.0',
        'qrcode>=6.1',
        'typer>=0.9.0',
    ],
    extras_require={
        'classic': ['PyBluez>=0.23'],
        'ble': ['bleak>=0.20.0'],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',      # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    entry_points={
        'console_scripts': [
            'peripage = peripage.cli:main'
        ]
    }
)

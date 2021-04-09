# Create a container image from a cuda image
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# JSON manifest
ARG MANIFEST
LABEL "up42_manifest"=${MANIFEST}

# Install dependencies
RUN yum update -y && \
    yum install -y gdal gdal-devel && \
    pip3 install --no-cache-dir rasterio pyproj requests geojson Pillow==7.2.0

# Copy application and models
COPY . /block/

# Set permissions
RUN chmod -R 777 /block

# Set workdir
ARG WORKDIR
ENV WORKDIR ${WORKDIR}
WORKDIR ${WORKDIR}

# Run command
ARG RUN_COMMAND
ARG PORT
ARG PROCESS_ROUTE
ARG HEALTHCHECK_ROUTE
ARG TYPE
ARG RESOLUTION

ENV RUN_COMMAND ${RUN_COMMAND}
ENV PORT ${PORT}
ENV PROCESS_ROUTE ${PROCESS_ROUTE}
ENV HEALTHCHECK_ROUTE ${HEALTHCHECK_ROUTE}
ENV TYPE ${TYPE}
ENV RESOLUTION ${RESOLUTION}


ENTRYPOINT ["/bin/bash", "-c", "/block/run_command.sh ${PORT} ${PROCESS_ROUTE} ${HEALTHCHECK_ROUTE} ${TYPE} ${RESOLUTION} ${RUN_COMMAND}"]
# CMD ["/bin/bash", "-c", "/block/run_command.sh ${PORT} ${PROCESS_ROUTE} ${HEALTHCHECK_ROUTE} ${TYPE} ${RUN_COMMAND}"]

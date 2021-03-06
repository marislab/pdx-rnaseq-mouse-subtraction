from util.varsub import varsub

configfile: "config.yaml"
varsub(config)

shell.prefix("source ~/.bash_profile")

# os.environ['LD_LIBRARY_PATH'] = config['ld_path']

with open(config['samples']) as f:
	SAMPLES = f.read().splitlines()
	print(SAMPLES)

rule all:
	input:
		config['data']['ref']['genomedir'] + "SAindex",
		config['data']['ref']['dictfiledir'] + "Homo_sapiens.GRCh37.71.hap.ERCC.sm.fa.dict",
		expand(config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}.bam.bai", file = SAMPLES),
		expand(config['dirs']['outdirs']['htseqdir'] + "{file}_star_hybrid.counts", file = SAMPLES),
		expand(config['dirs']['outdirs']['cufflinksdir'] + "{file}" + "/" + "genes.fpkm_tracking", file = SAMPLES),
		expand(config['dirs']['outdirs']['rnaseqcdir'] + "{file}" + "/" + "metrics.tsv", file = SAMPLES),
		config['data']['ref']['transcripts_dictfiledir'] + "protein_coding_canonical.T_chr.fa.dict",
		expand(config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_transcript.bam.bai",file = SAMPLES),
		expand(config['dirs']['outdirs']['pindeldir'] + "{file}" + "/", file = SAMPLES)


# star genome
rule star_hg19_genome:
	input:
		genomefile = config['data']['ref']['genomefile']
	output:
		genomedir = config['data']['ref']['genomedir'],
		genomedir_index = config['data']['ref']['genomedir'] + "SAindex"
	log:
		out = config['dirs']['logdir'] + "star_hg19_genome.log",
		err = config['dirs']['logdir'] + "star_hg19_genome.err"
	params:
		star = config['tools']['star'],
		gtf = config['data']['annotation']['gtf']
	threads: 4
	shell:
		"""
		mkdir -p {output.genomedir}

		{params.star} \
		--runMode genomeGenerate \
		--genomeDir {output.genomedir} \
		--outFileNamePrefix {output.genomedir} \
		--runThreadN 4 \
		--genomeFastaFiles {input.genomefile} \
		--sjdbOverhang 100 \
		--sjdbGTFfile {params.gtf} 2> {log.err} 1> {log.out}
		"""

# star
rule star_realign:
	input:
		fq1 = config['dirs']['outdirs']['bamhybrid'] + "{file}" + "/" + "{file}_hybrid_hg19_1_sequence.txt.bz2",
		fq2 = config['dirs']['outdirs']['bamhybrid'] + "{file}" + "/" + "{file}_hybrid_hg19_2_sequence.txt.bz2",
		genomedir = config['data']['ref']['genomedir'],
		genomedir_index = config['data']['ref']['genomedir'] + "SAindex"
	output:
		bam = temp(config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}_star.bam")
	log:
		out = config['dirs']['logdir'] + "{file}" + "_star_realign.log",
		err = config['dirs']['logdir'] + "{file}" + "_star_realign.err"
	params:
		star = config['tools']['star'],
		samtools = config['tools']['samtools'],
		genomedir = config['data']['ref']['genomedir'],
		realign = config['dirs']['outdirs']['realign'] + "{file}" + "/",
		outprefix = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}_"
	threads: 4
	shell:
		"""
		mkdir -p {params.realign}

		{params.star} \
		--genomeDir {params.genomedir} \
		--outFileNamePrefix {params.outprefix} \
		--readFilesIn {input.fq1} {input.fq2} \
		--readFilesCommand "bzcat" \
		--chimSegmentMin 18 \
		--chimScoreMin 12 \
		--runThreadN 8 \
		--outFilterMultimapNmax 20 \
		--outFilterMismatchNoverLmax 0.04 \
		--outFilterIntronMotifs RemoveNoncanonicalUnannotated \
		--alignIntronMax 200000 \
		--outSAMstrandField intronMotif \
		--outStd SAM \
		--outSAMunmapped Within | {params.samtools} view - -b -S -o {output.bam} 2> {log.err} 1> {log.out}
		"""

# add or replace read groups 
rule addreadgroups:
	input:
		bam = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}_star.bam"
	output:
		bam = temp(config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}_star.sorted.bam")
	log:
		out = config['dirs']['logdir'] + "{file}" + "_addreadgroups.log",
		err = config['dirs']['logdir'] + "{file}" + "_addreadgroups.err"
	params:
		java = config['binaries']['java'],
		picard = config['tools']['picard'],
		sample = "{file}",
		library = "fastq",
		puid = "123",
		tmpdir = config['dirs']['tmpdir']
	threads: 2
	shell:
		"""
		{params.java} \
		-Xmx22G \
		-jar {params.picard}/picard.jar AddOrReplaceReadGroups \
		INPUT={input.bam} OUTPUT={output.bam} \
		SORT_ORDER=coordinate \
		RGID="{params.sample}" \
		RGLB="{params.library}" \
		RGPL="Illumina" \
		RGSM="{params.sample}" \
		RGCN="BCM" \
		RGPU="{params.puid}" \
		TMP_DIR={params.tmpdir} \
		MAX_RECORDS_IN_RAM=3000000 \
		VALIDATION_STRINGENCY=SILENT 2> {log.err} 1> {log.out}
		"""

# create sequence dictionary
rule sequence_dict:
	input:
		genomefile = config['data']['ref']['genomefile']
	output:
		dict = config['data']['ref']['dictfiledir'] + "Homo_sapiens.GRCh37.71.hap.ERCC.sm.fa.dict"
	log:
		out = config['dirs']['logdir'] + "sequence_dict.log",
		err = config['dirs']['logdir'] + "sequence_dict.err"
	params:
		java = config['binaries']['java'],
		picard = config['tools']['picard']
	threads: 2
	shell:
		"""
		{params.java} -Xmx4g -jar {params.picard}/picard.jar CreateSequenceDictionary \
		R={input.genomefile} \
		O={output.dict} 2> {log.err} 1> {log.out}
		"""

# reorder sam file
rule reordersam:
	input:
		bam = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}_star.sorted.bam",
		dict = config['data']['ref']['dictfiledir'] + "Homo_sapiens.GRCh37.71.hap.ERCC.sm.fa.dict"
	output:
		bam = temp(config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}_duplicates.bam")
	log:
		out = config['dirs']['logdir'] + "{file}" + "_reordersam.log",
		err = config['dirs']['logdir'] + "{file}" + "_reordersam.err"
	params:
		java = config['binaries']['java'],
		picard = config['tools']['picard'],
		tmpdir = config['dirs']['tmpdir'],
		genomefile = config['data']['ref']['genomefile']
	threads: 2
	shell:
		"""
		{params.java} \
		-Xmx4g \
		-jar {params.picard}/picard.jar ReorderSam \
		I={input.bam} O={output.bam} \
		REFERENCE={params.genomefile} \
		TMP_DIR={params.tmpdir} \
		MAX_RECORDS_IN_RAM=3000000 \
		VALIDATION_STRINGENCY=SILENT 2> {log.err} 1> {log.out}
		"""

# mark duplicates
rule markdups:
	input:
		bam = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}_duplicates.bam"
	output:
		bam = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}.bam",
		stats = config['dirs']['outdirs']['realignstats'] + "{file}" + "/" + "{file}_metrics.txt"
	log:
		out = config['dirs']['logdir'] + "{file}" + "_markdups.log",
		err = config['dirs']['logdir'] + "{file}" + "_markdups.err"
	params:
		realignstats = config['dirs']['outdirs']['realignstats'] + "{file}" + "/",
		java = config['binaries']['java'],
		picard = config['tools']['picard'],
		tmpdir = config['dirs']['tmpdir'],
	threads: 2
	shell:
		"""
		mkdir -p {params.realignstats}

		{params.java} \
		-Xmx4g \
		-jar {params.picard}/picard.jar MarkDuplicates \
		I={input.bam} O={output.bam} \
		AS=true M={output.stats} \
		TMP_DIR={params.tmpdir} \
		MAX_RECORDS_IN_RAM=3000000 \
		VALIDATION_STRINGENCY=SILENT 2> {log.err} 1> {log.out}
		"""

# index bamfile
rule indexbam:
	input:
		bam = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}.bam"
	output:
		bai = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}.bam.bai"
	log:
		out = config['dirs']['logdir'] + "{file}" + "_indexbam.log",
		err = config['dirs']['logdir'] + "{file}" + "_indexbam.err"
	params:
		samtools = config['tools']['samtools']
	threads: 2
	shell:
		"""
		{params.samtools} index {input.bam} 2> {log.err} 1> {log.out}
		"""

# htseq
rule htseq:
	input:
		bam = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}.bam"
	output:
		counts = config['dirs']['outdirs']['htseqdir'] + "{file}_star_hybrid.counts"
	log:
		out = config['dirs']['logdir'] + "{file}" + "_htseq.log",
		err = config['dirs']['logdir'] + "{file}" + "_htseq.err"
	params:
		callhtseq = config['tools']['callhtseq'],
		gtf_htseq = config['data']['annotation']['gtf_htseq'],
		tmpdir = config['mytmpdir'],
		htseqdir = config['dirs']['outdirs']['htseqdir']
	threads: 2
	shell:
		"""
		mkdir -p {params.htseqdir}
		
		{params.callhtseq} {input.bam} {params.gtf_htseq} {output.counts} {params.tmpdir} 2> {log.err} 1> {log.out}
		"""

# qcmetrics - error here
rule qcmetrics:
	input:
		bam = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}.bam"
	output:
		rnaseqcdir = config['dirs']['outdirs']['rnaseqcdir'] + "{file}" + "/",
		txt = config['dirs']['outdirs']['rnaseqcdir'] + "{file}" + "/" + "{file}_sample_file.txt",
		metrics = config['dirs']['outdirs']['rnaseqcdir'] + "{file}" + "/" + "metrics.tsv"
	log:
		out = config['dirs']['logdir'] + "{file}" + "_qcmetrics.log",
		err = config['dirs']['logdir'] + "{file}" + "_qcmetrics.err"
	params:
		sample = "{file}",
		rnaseqcdir = config['dirs']['outdirs']['rnaseqcdir'],
		java = config['binaries']['java_rnaseqc'],
		rnaseqQC = config['tools']['rnaseqQC'],
		genomefile = config['data']['ref']['genomefile'],
		gtf = config['data']['annotation']['gtf']
	threads: 2
	shell:
		"""
		mkdir -p {params.rnaseqcdir}

		echo -e "Sample ID\tBam File\tNotes" > {output.txt} 
		echo -e "{params.sample}\t{input.bam}\tRNA-Seq-stats" >> {output.txt}

		{params.java} \
		-Xmx5g \
		-jar {params.rnaseqQC} \
		-s {output.txt} \
		-t {params.gtf} -r {params.genomefile} -o {output.rnaseqcdir} 2> {log.err} 1> {log.out}
		"""

# cufflinks
rule cufflinks:
	input:
		bam = config['dirs']['outdirs']['realign'] + "{file}" + "/" + "{file}.bam"
	output:
		cufflinksdir = config['dirs']['outdirs']['cufflinksdir'] + "{file}" + "/",
		cufflinks_out = config['dirs']['outdirs']['cufflinksdir'] + "{file}" + "/" + "genes.fpkm_tracking"
	log:
		out = config['dirs']['logdir'] + "{file}" + "_cufflinks.log",
		err = config['dirs']['logdir'] + "{file}" + "_cufflinks.err"
	params:
		cufflinksdir = config['dirs']['outdirs']['cufflinksdir'],
		cufflinks = config['tools']['cufflinks'],
		gtf = config['data']['annotation']['gtf']
	threads: 2
	shell:
		"""
		mkdir -p {params.cufflinksdir}

		{params.cufflinks} \
		-G {params.gtf} {input.bam} \
		-q -o {output.cufflinksdir} \
		-p 4 --no-update-check 2> {log.err} 1> {log.out}
		"""

# bwa_mem
rule bwa_mem:
	input:
		fq1 = config['dirs']['outdirs']['bamhybrid'] + "{file}" + "/" + "{file}_hybrid_hg19_1_sequence.txt.bz2",
		fq2 = config['dirs']['outdirs']['bamhybrid'] + "{file}" + "/" + "{file}_hybrid_hg19_2_sequence.txt.bz2"
	output:
		bam = temp(config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_bwa.bam")
	log:
		out = config['dirs']['logdir'] + "{file}" + "_bwamem.log",
		err = config['dirs']['logdir'] + "{file}" + "_bwamem.err"
	params:
		bwaalign = config['dirs']['outdirs']['bwaalign'] + "{file}" + "/",
		bwa = config['tools']['bwa'],
		transcripts = config['data']['ref']['transcripts'],
		bzip2 = config['binaries']['bzip2'],
		samtools = config['tools']['samtools']
	threads: 4
	shell:
		"""
		mkdir -p {params.bwaalign}

		{params.bwa} mem -M -T 0 -t 6 \
		{params.transcripts} <({params.bzip2} -dc {input.fq1}) <({params.bzip2} -dc {input.fq2}) | \
		{params.samtools} view - -b -S -o {output.bam} 2> {log.err} 1> {log.out}
		"""

# add or replace read groups 
rule bwa_mem_addreadgroups:
	input:
		bam = config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_bwa.bam"
	output:
		bam = temp(config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_bwa.sorted.bam")
	log:
		out = config['dirs']['logdir'] + "{file}" + "_bwa_mem_addreadgroups.log",
		err = config['dirs']['logdir'] + "{file}" + "_bwa_mem_addreadgroups.err"
	params:
		java = config['binaries']['java'],
		picard = config['tools']['picard'],
		sample = "{file}",
		library = "fastq",
		puid = "1234",
		tmpdir = config['dirs']['tmpdir']
	threads: 2
	shell:
		"""
		{params.java} \
		-Xmx22G \
		-jar {params.picard}/picard.jar AddOrReplaceReadGroups \
		INPUT={input.bam} OUTPUT={output.bam} \
		SORT_ORDER=coordinate \
		RGID="{params.sample}" \
		RGLB="{params.library}" \
		RGPL="Illumina" \
		RGSM="{params.sample}" \
		RGCN="BCM" RGPU="{params.puid}" \
		TMP_DIR={params.tmpdir} \
		MAX_RECORDS_IN_RAM=3000000 \
		VALIDATION_STRINGENCY=SILENT 2> {log.err} 1> {log.out}
		"""

# create sequence dictionary
rule bwa_sequence_dict:
	input:
		transcripts = config['data']['ref']['transcripts']
	output:
		transcripts_dictfiledir = config['data']['ref']['transcripts_dictfiledir'] + "protein_coding_canonical.T_chr.fa.dict"
	log:
		out = config['dirs']['logdir'] + "bwa_sequence_dict.log",
		err = config['dirs']['logdir'] + "bwa_sequence_dict.err"
	params:
		java = config['binaries']['java'],
		picard = config['tools']['picard']
	threads: 2
	shell:
		"""
		{params.java} -Xmx4g -jar {params.picard}/picard.jar CreateSequenceDictionary \
		R={input.transcripts} \
		O={output.transcripts_dictfiledir} 2> {log.err} 1> {log.out}
		"""

# reorder sam file
rule bwa_mem_reordersam:
	input:
		bam = config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_bwa.sorted.bam",
		transcripts_dictfiledir = config['data']['ref']['transcripts_dictfiledir'] + "protein_coding_canonical.T_chr.fa.dict"
	output:
		bam = temp(config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_duplicates_bwa.bam")
	log:
		out = config['dirs']['logdir'] + "{file}" + "_bwa_mem_reordersam.log",
		err = config['dirs']['logdir'] + "{file}" + "_bwa_mem_reordersam.err"
	params:
		java = config['binaries']['java'],
		picard = config['tools']['picard'],
		tmpdir = config['dirs']['tmpdir'],
		transcripts = config['data']['ref']['transcripts']
	threads: 2
	shell:
		"""
		{params.java} \
		-Xmx4g \
		-jar {params.picard}/picard.jar ReorderSam \
		I={input.bam} O={output.bam} \
		REFERENCE={params.transcripts} \
		TMP_DIR={params.tmpdir} \
		MAX_RECORDS_IN_RAM=3000000 \
		VALIDATION_STRINGENCY=SILENT 2> {log.err} 1> {log.out}
		"""

# mark duplicates
rule bwa_mem_markdups:
	input:
		bam = config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_duplicates_bwa.bam"
	output:
		bam = config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_transcript.bam",
		stats = config['dirs']['outdirs']['bwaalignstats'] + "{file}" + "/" + "{file}_metrics_bwa.txt"
	log:
		out = config['dirs']['logdir'] + "{file}" + "_bwa_mem_markdups.log",
		err = config['dirs']['logdir'] + "{file}" + "_bwa_mem_markdups.err"
	params:
		bwaalignstats = config['dirs']['outdirs']['bwaalignstats'] + "{file}" + "/",
		java = config['binaries']['java'],
		picard = config['tools']['picard'],
		tmpdir = config['dirs']['tmpdir']
	threads: 2
	shell:
		"""
		mkdir -p {params.bwaalignstats}

		{params.java} \
		-Xmx4g \
		-jar {params.picard}/picard.jar MarkDuplicates \
		I={input.bam} O={output.bam} \
		AS=true M={output.stats} \
		TMP_DIR={params.tmpdir} \
		MAX_RECORDS_IN_RAM=3000000 \
		VALIDATION_STRINGENCY=SILENT 2> {log.err} 1> {log.out}
		"""

# index bamfile
rule bwa_mem_indexbam:
	input:
		bam = config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_transcript.bam"
	output:
		bai = config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_transcript.bam.bai"
	log:
		out = config['dirs']['logdir'] + "{file}" + "_bwa_mem_indexbam.log",
		err = config['dirs']['logdir'] + "{file}" + "_bwa_mem_indexbam.err"
	params:
		samtools = config['tools']['samtools']
	threads: 2
	shell:
		"""
		{params.samtools} index {input.bam} 2> {log.err} 1> {log.out}
		"""

# pindel
rule pindel:
	input:
		bam = config['dirs']['outdirs']['bwaalign'] + "{file}" + "/" + "{file}_transcript.bam"
	output:
		pindeldir = config['dirs']['outdirs']['pindeldir'] + "{file}" + "/",
		txt = config['dirs']['outdirs']['pindeldir'] + "{file}" + "/" + "{file}_pindel_input.txt"
	log:
		out = config['dirs']['logdir'] + "{file}" + "_pindel.log",
		err = config['dirs']['logdir'] + "{file}" + "_pindel.err"
	params:
		sample = "{file}",
		pindeldir = config['dirs']['outdirs']['pindeldir'],
		pindel = config['tools']['pindel'],
		transcripts = config['data']['ref']['transcripts']
	threads: 2
	shell:
		"""
		mkdir -p {params.pindeldir}

		echo -e "{input.bam}\t250\t{params.sample}" > {output.txt}
		{params.pindel} -f {params.transcripts} -i {output.txt} -c ALL -o {output.pindeldir} 2> {log.err} 1> {log.out}
		"""
